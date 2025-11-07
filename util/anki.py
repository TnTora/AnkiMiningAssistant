import re
import json
import urllib.request
import urllib.error
import threading
from pathlib import Path
from time import sleep
from datetime import datetime
from copy import copy
import traceback
import soundfile as sf
from itertools import islice

from PySide6.QtCore import QObject, Signal

import util.sockets
from util import audio
from util import screenshot
from util.database import AnkiSettings, settings, sessionsdb

previous_notes = set()
last_note = None
last_note_update_time = None
last_note_info = None
last_note_sentence_clean = None

start_session = datetime.now()


class AnkiSignals(QObject):
    anki_status = Signal(int)
    last_note_changed = Signal(str, str)
    note_update_info = Signal(str)
    note_update_select_line = Signal(list)
    note_update_confirm = Signal(list, object, tuple, str)
    # note_update_confirm_audio = Signal(list, list, tuple, str)

    wait_event = None
    returned_value = None

    def wait_result(self) -> None:
        self.returned_value = None
        self.wait_event = threading.Event()
        self.wait_event.wait()
        tmp_result = self.returned_value
        self.returned_value = None
        return tmp_result


anki_signals = AnkiSignals()


def request(action, **params):
    return {"action": action, "params": params, "version": 6}


def invoke(action, **params):
    try:
        requestJson = json.dumps(request(action, **params)).encode("utf-8")
        response = json.load(urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{AnkiSettings.port}", requestJson)))
        if len(response) != 2:  # noqa: PLR2004
            raise Exception("response has an unexpected number of fields")
        if "error" not in response:
            raise Exception("response is missing required error field")
        if "result" not in response:
            raise Exception("response is missing required result field")
        if response["error"] is not None:
            raise Exception(response["error"])
        return response["result"]
    except Exception:
        # traceback.print_exc()
        return None


def get_media_dir():
    results = invoke("getMediaDirPath")
    return results


def get_note_types():
    results = invoke("modelNames")
    return results


def get_note_types_fields(name):
    results = invoke("modelFieldNames", modelName=name)
    return results


def get_all_note_types_fields(names):
    results = invoke("findModelsByName", modelNames=names)
    fields_dict = {result["name"]: [field["name"] for field in result["flds"]] for result in results}
    return fields_dict


def get_last_note():
    results = invoke("findNotes", query=f"deck:{AnkiSettings.deck} added:1")
    if results:
        return max(results)
    raise Exception("No note found")


def get_note_info(note):
    results = invoke("notesInfo", notes=[note])
    note_type = results[0]["modelName"]

    if note_type not in AnkiSettings.note_types:
        return None

    infos = {
        "noteType": note_type,
        "Expression": results[0]["fields"][AnkiSettings.expression[note_type]]["value"],
        "Sentence": results[0]["fields"][AnkiSettings.sentence[note_type]]["value"],
        "Picture": results[0]["fields"][AnkiSettings.picture[note_type]]["value"],
        "SentenceAudio": results[0]["fields"][AnkiSettings.sentence_audio[note_type]]["value"],
    }
    return infos


def update_note(note_id, fields, tags=""):
    invoke("guiSelectNote", note=1)
    invoke("updateNoteFields", note={"id": note_id, "fields": fields})
    if tags:
        invoke("addTags", notes=[note_id], tags=tags)
    if sessionsdb.current_session["open_in_browser"]:
        invoke("guiBrowse", query=f"nid:{note_id}")


def manual_update_note(*, update_img: bool = True, update_audio: bool = True) -> None:  # noqa: C901
    if last_note is None:
        anki_signals.note_update_info.emit("No note selected")
        return

    update_fields = {}
    curr_time = datetime.now()

    img_path = Path(AnkiSettings.media_dir) / f"{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.webp"
    audio_path = Path(AnkiSettings.media_dir) / f"{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.mp3"

    if update_img:
        screenshot._take_screenshot(curr_time, save_path=img_path)  # noqa: SLF001
        update_fields[AnkiSettings.picture[last_note_info["noteType"]]] = f'<img alt="snapshot" src="{f"{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.webp"}">'

    if update_audio:
        # data_copy = list(audio.buffer.slice_())
        data_copy = audio.buffer.copy_slice()

        # Check for the first interval of no voice in the last 20 seconds (or less if not availables) to get interval_end
        # Then find a pause in the voice of at least pause_threshold to find interval_start

        interval_start = max(0, len(data_copy)-int(5/settings.audio.interval_duration))
        interval_end = len(data_copy)
        pause_threshold = 2
        margin = 0.2

        end_found = False
        pause = 0
        for i in range(len(data_copy)-1, len(data_copy) - int(20/settings.audio.interval_duration), -1):
            if not end_found:
                if data_copy[i].vad <= settings.audio.vad_threshold:
                    continue
                interval_end = min(interval_end, i + int(margin/settings.audio.interval_duration))
                end_found = True
                continue

            if data_copy[i].vad <= settings.audio.vad_threshold:
                pause += settings.audio.interval_duration
                if pause > pause_threshold:
                    interval_start = max(0, i + int(pause/settings.audio.interval_duration) - int(margin/settings.audio.interval_duration))
                continue

            pause = 0

        anki_signals.note_update_confirm.emit([], data_copy, (interval_start, interval_end), "")
        res = anki_signals.wait_result()

        if res is None:
            return

        _, audio_interval, _ = res

        if audio_interval:
            with sf.SoundFile(file=audio_path, mode="w", channels=audio.buffer.channels, samplerate=settings.audio.samplerate) as f:
                for interval in islice(data_copy, audio_interval[0], audio_interval[1]):
                    f.write(interval.data)
            update_fields[AnkiSettings.sentence_audio[last_note_info["noteType"]]] = f"[sound:{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.mp3]"

    if update_fields:
        update_note(last_note, update_fields)


def search_linesdb(sentence: str):
    found_lines = []
    found = False

    text_copy = copy(util.sockets.text_stored)

    for line in text_copy:

        if found:
            found_lines[-1]["next"] = line
            found = False

        substring_idx = line.text.find(sentence)

        if substring_idx == -1:
            continue

        found_lines.append({"line": line, "next": None})
        found = True

    if not found_lines:
        anki_signals.note_update_info.emit(f"No matches found for:\n{sentence}")
        return None

    if len(found_lines) > 1:
        anki_signals.note_update_select_line.emit(found_lines)
        selected_line_idx = anki_signals.wait_result()
        if selected_line_idx is None:
            return None
        selected_line = found_lines[selected_line_idx]
    else:
        selected_line = found_lines[0]

    return selected_line


def auto_update_note(*, update_img: bool = True, update_audio: bool = True, confirmation: bool = False) -> None:
    if last_note is None:
        anki_signals.note_update_info.emit("No note selected")
        return

    next_line_time = None
    images = []
    line_audio = (None)
    line_update = None

    selected_img = None
    update_fields = {}

    curr_time = datetime.now()

    if util.sockets.selected_idxs:
        selected_line = util.sockets.manual_line_selection(util.sockets.selected_idxs)
    else:
        selected_line = search_linesdb(last_note_sentence_clean)

    if selected_line is None:
        return

    if selected_line["next"]:
        next_line_time = selected_line["next"].time

    if update_img:
        for img in screenshot.images_tmp:
            if img.time < selected_line["line"].time:
                continue
            if selected_line["next"] and img.time > selected_line["next"].time:
                break
            images.append(img)

    if AnkiSettings.media_dir is None:
        media_dir = get_media_dir()
        if media_dir is None:
            return
        settings.update_option("anki", "media_dir", media_dir)

    img_path = Path(AnkiSettings.media_dir) / f"{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.webp"
    audio_path = Path(AnkiSettings.media_dir) / f"{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.mp3"

    if confirmation:
        buffer_copy = None
        audio_interval = None
        if update_audio:
            line_audio = audio.buffer.extract_line_audio(selected_line["line"].time, next_line_time)
            buffer_copy = line_audio[0]
            audio_interval = line_audio[1:]

        line_update = selected_line["line"].text.replace(last_note_sentence_clean, last_note_info["Sentence"])

        anki_signals.note_update_confirm.emit(images, buffer_copy, audio_interval, line_update)
        res = anki_signals.wait_result()

        if res is None:
            return

        selected_img_idx, audio_interval, line_update = res

        update_fields[AnkiSettings.sentence[last_note_info["noteType"]]] = line_update

        if selected_img_idx is not None:
            selected_img = images[selected_img_idx]

        if buffer_copy and audio_interval:
            with sf.SoundFile(file=audio_path, mode="w", channels=audio.buffer.channels, samplerate=settings.audio.samplerate) as f:
                for interval in islice(buffer_copy, audio_interval[0], audio_interval[1]):
                    f.write(interval.data)

    else:
        if update_audio:
            line_audio = audio.buffer.extract_line_audio(selected_line["line"].time, next_line_time, save_path=audio_path)

        if images:
            selected_img = images[0]

        if selected_line["line"].text != last_note_sentence_clean:
            line_update = selected_line["line"].text.replace(last_note_sentence_clean, last_note_info["Sentence"])
            update_fields[AnkiSettings.sentence[last_note_info["noteType"]]] = line_update

    if selected_img:
        with open(img_path, "wb") as f:
            f.write(selected_img.img_bytesIO.getbuffer())
        update_fields[AnkiSettings.picture[last_note_info["noteType"]]] = f'<img alt="snapshot" src="{f"{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.webp"}">'

    if line_audio[0]:
        update_fields[AnkiSettings.sentence_audio[last_note_info["noteType"]]] = f"[sound:{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.mp3]"

    if update_fields:
        update_note(last_note, update_fields)


CLEANER = re.compile("<.*?>")


def cleanhtml(raw_html):
    cleantext = re.sub(CLEANER, "", raw_html)
    return cleantext


def monitor_last_note(widget_info_update=None):
    global last_note, last_note_update_time, last_note_info, last_note_sentence_clean  # noqa: PLW0603
    first_fail = True
    while True:
        try:
            last_note_tmp = get_last_note()

            if last_note_tmp == last_note:
                continue

            last_note = last_note_tmp
            last_note_update_time = datetime.now()
            last_note_info = get_note_info(last_note)

            if last_note_info is None:
                continue

            last_note_sentence_clean = cleanhtml(last_note_info["Sentence"])
            anki_signals.last_note_changed.emit(last_note_info["Expression"], last_note_sentence_clean)

            if last_note_tmp not in previous_notes:
                previous_notes.add(last_note_tmp)
                if sessionsdb.current_session["auto_update"] and last_note > start_session.timestamp()*1000:
                    auto_update_note(confirmation=sessionsdb.current_session["preview_note"])

        except Exception as e:
            if "No note found" in str(e):
                if last_note is not None or first_fail:
                    first_fail = False
                    # print("No note found")
                    last_note = None
                    anki_signals.last_note_changed.emit("No note found", "")
            else:
                traceback.print_exc()
        finally:
            sleep(0.2)


def check_anki_status():
    while True:
        try:
            requestJson = json.dumps(request("version")).encode("utf-8")
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{AnkiSettings.port}", requestJson))
        except Exception:
            # TODO: Specify errors
            anki_signals.anki_status.emit(1)
        else:
            anki_signals.anki_status.emit(2)
        finally:
            sleep(1)


def start_monitoring_anki(widget_info_update=None):
    anki_thread = threading.Thread(target=monitor_last_note, args=[widget_info_update], daemon=True)
    anki_thread.start()
    status_thread = threading.Thread(target=check_anki_status, daemon=True)
    status_thread.start()


# TODO: Possibly merge following functions into a single one
def start_auto_note_update(update_img, update_audio, confirmation):
    update_thread = threading.Thread(
        target=auto_update_note,
        kwargs={"update_img": update_img, "update_audio": update_audio, "confirmation": confirmation},
        daemon=True
    )
    update_thread.start()
    return update_thread


def start_manual_note_update(update_img, update_audio):
    update_thread = threading.Thread(
        target=manual_update_note,
        kwargs={"update_img": update_img, "update_audio": update_audio},
        daemon=True
    )
    update_thread.start()
    return update_thread
