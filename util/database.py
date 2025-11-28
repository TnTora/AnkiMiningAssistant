import sqlite3
from datetime import timedelta
from contextlib import closing
from io import BytesIO
import soundfile as sf
import inspect
import json


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
    note_types = []
    expression = {}
    sentence = {}
    picture = {}
    sentence_audio = {}
    note_types_fields = {}


class AudioSettings:

    samplerate = 44100
    interval_duration = 512/16000
    inactivity_pause_timer = 10
    audio_input = None
    resume_on_detected_voice = False
    continuous_recording = False
    vad_threshold = 0.5
    pause_threshold = 10
    padding = 320


class ImageSettings:

    format = "WEBP"
    webp_quality = 80
    max_resolution = "1080p"
    capture_interval = 1
    pixel_ratio = None
    offsets = {
        "x": 0,
        "y": 0,
    }


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
        self.store_settings()

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
                    for option, _value in get_attributes(class_):
                        value_type = type(_value).__name__
                        value = _value
                        if value_type == "timedelta":
                            value = value.total_seconds()
                        if value_type in ["list", "dict"]:
                            value = json.dumps(value)
                        conn.execute("""
                            INSERT INTO settings (section, option, type, value)
                            VALUES (?, ?, ?, ?)
                        """, (section, option, value_type, value))

    def update_option(self, section, option, new_value):

        value_type = type(new_value).__name__

        section_class = getattr(self, section)
        old_value = getattr(section_class, option)
        if isinstance(old_value, timedelta) and isinstance(new_value, (int, float)):
            setattr(section_class, option, timedelta(seconds=new_value))
        elif (old_value is not None) and (type(old_value) is not type(new_value)):
            return
        else:
            setattr(section_class, option, new_value)

        if value_type == "timedelta":
            new_value = new_value.total_seconds()
        if value_type in ["list", "dict"]:
            new_value = json.dumps(new_value)

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
                for section, option, value_type, _value in fetch:
                    section_class = getattr(self, section)
                    value = _value
                    if value_type == "bool":
                        value = bool(_value)
                    if value_type == "timedelta":
                        value = timedelta(seconds=_value)
                    if value_type in ["list", "dict"]:
                        value = json.loads(_value)
                    setattr(section_class, option, value)
                    # print(f"section: {section_class}, option: {option}, value_type: {value_type}, value: {value}")


class ImageDB:

    def __init__(self, path) -> None:
        self.path = path
        self.last_loaded_timestamp = 0
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
        def insert_img_gen(img_buffer):
            for img in img_buffer:
                if img.time.timestamp() <= self.last_loaded_timestamp:
                    continue
                yield (img.time.timestamp(), img.img_bytesIO.getbuffer())

        with closing(sqlite3.connect(self.path)) as conn:
            if len(img_buffer) == 0:
                return
            with conn:
                conn.execute("""
                    DELETE FROM images
                    WHERE time < ?;
                """, (img_buffer[0].time.timestamp(),))

                conn.executemany("""
                    INSERT INTO images (time, data)
                    VALUES (?, ?);
                """, insert_img_gen(img_buffer))

    def load_imgs(self):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                for data, timestamp in conn.execute("SELECT data, time FROM images ORDER BY time ASC;"):
                    self.last_loaded_timestamp = timestamp
                    yield data, timestamp


class AudioDB:

    def __init__(self, path) -> None:
        self.path = path
        self.last_loaded_timestamp = 0
        self.create_tables()

    def create_tables(self):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS audio (
                            type      TEXT,
                            data      BLOB,
                            vad       REAL,
                            timestamp REAL PRIMARY KEY
                );""")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS inactive_intervals (
                            start     REAL,
                            end
                );""")

    def clear(self):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                conn.execute("""
                    DELETE FROM audio
                    WHERE type = 'interval'
                """)
                conn.execute("DELETE FROM inactive_intervals;")

    def store_buffer_intervals(self, buffer):
        def insert_audio_gen(audio_buffer):
            for interval in buffer:
                if interval.timestamp <= self.last_loaded_timestamp:
                    continue
                # print(f"self.last_loaded_timestamp: {self.last_loaded_timestamp}; interval.timestamp: {interval.timestamp}")

                temp_audio = BytesIO()

                audio_format = "WAV"
                if "MP3" in sf.available_formats():
                    audio_format = "MP3"

                with sf.SoundFile(temp_audio, mode="w", format=audio_format, channels=buffer.channels, samplerate=AudioSettings.samplerate) as f:
                    f.write(interval.data)

                yield ("interval", temp_audio.getbuffer(), interval.vad, interval.timestamp)

        if buffer is None or len(buffer) == 0:
            return
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:

                conn.execute("""
                    DELETE FROM audio
                    WHERE type = 'interval'
                    AND timestamp < ?
                """, (buffer[0].timestamp, ))

                conn.executemany("""
                    INSERT INTO audio (type, data, vad, timestamp)
                    VALUES (?, ?, ?, ?);
                """, insert_audio_gen(buffer))

    def store_inactive_intervals(self, buffer):
        def insert_inactive_gen(intervals):
            for interval in buffer.inactive_intervals:
                start = interval.start_time.timestamp()

                try:
                    end = interval.end_time.timestamp()
                except AttributeError:
                    end = None

                yield (start, end)

        if buffer is None or len(buffer) == 0:
            return
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                conn.execute("DELETE FROM inactive_intervals;")

                conn.executemany("""
                    INSERT INTO inactive_intervals (start, end)
                    VALUES (?, ?);
                """, insert_inactive_gen(buffer.inactive_intervals))

    def load_buffer_intervals(self):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                for data, vad, timestamp in conn.execute("""
                    SELECT data, vad, timestamp FROM audio
                    WHERE type = 'interval'
                    ORDER BY timestamp ASC;
                """):
                    self.last_loaded_timestamp = timestamp
                    interval_data, _ = sf.read(BytesIO(data))
                    if len(interval_data.shape) == 1:
                        interval_data = interval_data.reshape((-1, 1))
                    yield interval_data, vad, timestamp

    def load_inactive_intervals(self):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                yield from conn.execute("SELECT start, end FROM inactive_intervals;")


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

                line_storage.trim_extra()
                conn.executemany("""
                    INSERT INTO lines (time, text)
                    VALUES (?, ?);
                """, ((line.time.timestamp(), line.text) for line in line_storage))

    def load_lines(self):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                yield from conn.execute("SELECT text, time FROM lines ORDER BY time ASC")


class SessionDB:

    def __init__(self, path) -> None:
        self.path = path
        self.sessions_dict = {}
        self.current_session = None
        self.create_table()
        self.load_sessions()
        if "Manual" not in self.sessions_dict:
            self.sessions_dict["Manual"] = {
                "AppName": "",
                "WindowTitle": "",
                "continuous_recording": True,
                "auto_update": False,
                "open_in_browser": True,
                "preview_note": False,
                "use_screen_region": False,
                "screen_region": (0, 0, 0, 0),
            }
        try:
            self.current_session = self.sessions_dict[GeneralSettings.last_session]
        except KeyError:
            self.current_session = self.sessions_dict["Manual"]

    def create_table(self):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                            name            TEXT PRIMARY KEY,
                            AppName         TEXT,
                            WindowTitle     TEXT,
                            continuous_recording BOOLEAN,
                            auto_update     BOOLEAN,
                            open_in_browser BOOLEAN,
                            preview_note    BOOLEAN,
                            use_screen_region BOOLEAN,
                            screen_region
                );""")

    def store_sessions(self):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                conn.execute("DELETE FROM sessions;")
                for name, session in self.sessions_dict.items():
                    session["screen_region"] = json.dumps(session["screen_region"])
                    conn.execute("""
                        INSERT INTO sessions (name, AppName, WindowTitle, continuous_recording, auto_update, open_in_browser, preview_note, use_screen_region, screen_region)
                        VALUES (:name, :AppName, :WindowTitle, :continuous_recording, :auto_update, :open_in_browser, :preview_note, :use_screen_region, :screen_region);
                    """, {"name": name} | session)

    def load_sessions(self):
        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                for name, a_name, w_title, c_rec, a_up, open_gui, preview_note, use_screen_region, screen_region in conn.execute("""
                    SELECT name, AppName, WindowTitle, continuous_recording, auto_update, open_in_browser, preview_note, use_screen_region, screen_region FROM sessions
                """):
                    self.sessions_dict[name] = {
                        "AppName": a_name,
                        "WindowTitle": w_title,
                        "continuous_recording": c_rec,
                        "auto_update": a_up,
                        "open_in_browser": open_gui,
                        "preview_note": preview_note,
                        "use_screen_region": use_screen_region,
                        "screen_region": tuple(json.loads(screen_region))
                    }


settings = Settings("database.db")
imagedb = ImageDB("database.db")
audiodb = AudioDB("database.db")
linedb = LineDB("database.db")
sessionsdb = SessionDB("database.db")
