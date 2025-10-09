import sqlite3
from datetime import timedelta
from contextlib import closing
from io import BytesIO
import soundfile as sf
# import numpy as np
import inspect


class GeneralSettings:

    last_session = None
    storage_time_limit = timedelta(minutes=5, seconds=0)
    ws_port = 6678
    listen_urls = ["localhost:6677", "localhost:2333"]


class AnkiSettings:

    port = 8765
    media_dir = None
    auto_update_last_note = True
    open_note_in_gui = True
    deck = "*"
    note_types = ["Lapis"]
    expression = {
        "Lapis": "Expression",
    }
    sentence = {
        "Lapis": "Sentence",
    }
    picture = {
        "Lapis": "Picture",
    }
    sentence_audio = {
        "Lapis": "SentenceAudio",
    }
    note_types_fields = {}


class AudioSettings:

    samplerate = 44100
    interval_duration = 512/16000
    mic = None
    resume_on_detected_voice = False
    continuous_recording = False


class ImageSettings:

    format = "WEBP"
    webp_quality = 80
    max_resolution = "1080p"
    capture_interval = 1


def get_attributes(class_):
    for a in vars(class_).items():
        if inspect.isroutine(a[1]):
            continue
        if a[0].startswith("__") and a[0].endswith("__"):
            continue
        yield a


class Settings:

    def __init__(self, path) -> None:
        self.path = path
        self.general = GeneralSettings
        self.anki = AnkiSettings
        self.audio = AudioSettings
        self.image = ImageSettings
        self.create_table()
        self.load_settings()

    def create_table(self):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS settings (
                                section      TEXT,
                                option       TEXT,
                                type         TEXT,
                                value
                );""")

    def store_settings(self):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                conn.execute("DELETE FROM settings;")
                for section, class_ in get_attributes(self):
                    if not inspect.isclass(class_):
                        continue
                    for option, value in get_attributes(class_):
                        value_type = type(value).__name__
                        if value_type == "timedelta":
                            value = value.total_seconds()
                        if value_type == "list":
                            value = ",".join(value)
                        if value_type == "dict":
                            value = ",".join([f"{key}:{val}" for key, val in value.items()])
                        conn.execute("""
                            INSERT INTO settings (section, option, type, value)
                            VALUES (?, ?, ?, ?)
                        """, (section, option, value_type, value))

    def update_option(self, section, option, new_value):

        section_class = getattr(self, section)
        if type(new_value).__name__ == "timedelta":
            new_value = timedelta(seconds=new_value)
        setattr(section_class, option, new_value)

        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                conn.execute("""
                    UPDATE settings
                    SET value = :value
                    WHERE section = :section AND option = :option;
                """, {"value": new_value, "section": section, "option": option})

    def load_settings(self):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                fetch = conn.execute("SELECT section, option, type, value FROM settings")
                for section, option, value_type, value in fetch:
                    section_class = getattr(self, section)
                    if value_type == "timedelta":
                        value = timedelta(seconds=value)
                    if value_type == "list":
                        value = value.split(",")
                    if value_type == "dict":
                        if "," not in value:
                            value = {}
                        else:
                            value = {key: val for key, val in (tuple(a.split(":")) for a in value.split(","))}
                    setattr(section_class, option, value)
                    # print(f"section: {section_class}, option: {option}, value_type: {value_type}, value: {value}")


class ImageDB:

    def __init__(self, path) -> None:
        self.path = path
        self.create_table()

    def create_table(self):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS images (
                            time      REAL PRIMARY KEY,
                            data      BLOB
                );""")

    def store_imgs(self, img_buffer):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                conn.execute("DELETE FROM images;")
                for img in img_buffer:
                    conn.execute("""
                        INSERT INTO images (time, data)
                        VALUES (?, ?);
                    """, (img.time.timestamp(), img.img_bytesIO.getbuffer()))

    def load_imgs(self):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                for data in conn.execute("SELECT data, time FROM images;"):
                    yield data


class AudioDB:

    def __init__(self, path) -> None:
        self.path = path
        self.create_tables()

    def create_tables(self):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS audio (
                            type      TEXT,
                            data      BLOB,
                            vad       REAL
                );""")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS inactive_intervals (
                            start     REAL,
                            end
                );""")

    def store_buffer_intervals(self, buffer):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:

                conn.execute("DELETE FROM audio;")

                for interval in buffer:
                    temp_audio = BytesIO()

                    with sf.SoundFile(temp_audio, mode="w", format="WAV", channels=buffer.channels, samplerate=AudioSettings.samplerate) as f:
                        f.write(interval.data)

                    conn.execute("""
                        INSERT INTO audio (type, data, vad)
                        VALUES (?, ?, ?);
                    """, ("interval", temp_audio.getbuffer(), interval.vad))

    def store_buffer(self, buffer):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:

                conn.execute("DELETE FROM audio;")
                conn.execute("DELETE FROM inactive_intervals;")

                temp_audio = BytesIO()

                format = "WAV"
                if "MP3" in sf.available_formats():
                    format = "MP3"

                with sf.SoundFile(temp_audio, mode="w", format=format, channels=buffer.channels, samplerate=AudioSettings.samplerate) as f:
                    f.write(buffer.data)

                conn.execute("""
                    INSERT INTO audio (type, data)
                    VALUES (?, ?);
                """, ("full", temp_audio.getbuffer()))

                for interval in buffer:
                    conn.execute("""
                        INSERT INTO audio (type, vad)
                        VALUES (?, ?);
                    """, ("vad", interval.vad))

                for interval in buffer.inactive_intervals:
                    start = interval.start_time.timestamp()
                    # end = interval.end_time if not interval.end_time else interval.end_time.timestamp()

                    try:
                        end = interval.end_time.timestamp()
                    except AttributeError:
                        end = None

                    conn.execute("""
                        INSERT INTO inactive_intervals (start, end)
                        VALUES (?, ?);
                    """, (start, end))

    def load_buffer_intervals(self):
        result = None
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                result = list(conn.execute("SELECT data, vad FROM audio WHERE type = 'interval';"))
        return result

    def load_buffer_data(self):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                for data in conn.execute("SELECT data FROM audio WHERE type = 'full';"):
                    full_buffer, sr = sf.read(BytesIO(data[0]))
                    # intervals = np.split(full_buffer, full_buffer.shape[0]/int(sr*AudioSettings.interval_duration), axis=0)
                    chunk_size = int(sr*AudioSettings.interval_duration)
                    for i in range(0, full_buffer.shape[0], chunk_size):
                        yield full_buffer[i:i+chunk_size]

    def load_vad(self):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                for vad in conn.execute("SELECT vad FROM audio WHERE type = 'vad';"):
                    yield vad[0]

    def load_buffer(self):
        return zip(self.load_buffer_data(), self.load_vad())

    def load_inactive_intervals(self):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                for interval in conn.execute("SELECT start, end FROM inactive_intervals;"):
                    yield interval


class LineDB:

    def __init__(self, path) -> None:
        self.path = path
        self.create_table()

    def create_table(self):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS lines (
                            time      REAL PRIMARY KEY,
                            text      TEXT
                );""")

    def store_lines(self, line_storage):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                conn.execute("DELETE FROM lines;")
                for line in line_storage:
                    conn.execute("""
                        INSERT INTO lines (time, text)
                        VALUES (?, ?);
                    """, (line.time.timestamp(), line.text))

    def load_lines(self):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                for data in conn.execute("SELECT text, time FROM lines"):
                    yield data


class SessionDB:

    def __init__(self, path) -> None:
        self.path = path
        self.sessions_dict = {}
        self.create_table()
        self.load_sessions()
        if "Manual" not in self.sessions_dict:
            self.sessions_dict["Manual"] = {
                "AppName": "",
                "WindowTitle": "",
            }

    def create_table(self):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                            name            TEXT PRIMARY KEY,
                            AppName         TEXT,
                            WindowTitle     TEXT
                );""")

    def store_sessions(self):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                conn.execute("DELETE FROM sessions;")
                for name in self.sessions_dict:
                    conn.execute("""
                        INSERT INTO sessions (name, AppName, WindowTitle)
                        VALUES (?, ?, ?);
                    """, (name, self.sessions_dict[name]["AppName"], self.sessions_dict[name]["WindowTitle"]))

    def load_sessions(self):
        # sessions_dict = {}
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                for name, a_name, w_title in conn.execute("SELECT name, AppName, WindowTitle FROM sessions"):
                    self.sessions_dict[name] = {"AppName": a_name, "WindowTitle": w_title}
        # return self.sessions_dict


settings = Settings("database.db")
imagedb = ImageDB("database.db")
audiodb = AudioDB("database.db")
linedb = LineDB("database.db")
sessionsdb = SessionDB("database.db")
