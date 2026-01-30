import re
import json
import urllib.request
import urllib.error
import threading
from pathlib import Path
from time import sleep
from datetime import datetime
from copy import copy
# import traceback
import soundfile as sf
from itertools import islice
from enum import Enum

from PySide6.QtCore import QObject, Signal

from . import sockets as util_sockets
from util import audio
from util import screenshot
from util.database import AnkiSettings, settings, sessionsdb

from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections import deque

import logging

logger = logging.getLogger("app_logger")


class AnkiStatus(Enum):
    STOPPED = 0
    STARTED = 1
    CONNECTED = 2


CLEANER = re.compile("<.*?>")


def cleanhtml(raw_html: str) -> str:
    cleantext = re.sub(CLEANER, "", raw_html)
    return cleantext


class AnkiNote:

    def __init__(self, nid: int, info: dict[str, str]) -> None:
        self.nid: int = nid
        self.noteType: str = info["noteType"]
        self.Expression: str = info["Expression"]
        self.Sentence: str = info["Sentence"]
        self.Picture: str = info["Picture"]
        self.SentenceAudio: str = info["SentenceAudio"]

        self.SentenceClean: str = cleanhtml(self.Sentence)

    def __eq__(self, other) -> bool:
        if isinstance(other, int):
            return self.nid == other
        if isinstance(other, AnkiNote):
            return self.nid == other.nid
        return False

    def update(self, fields: dict[str, str], tags: list[str] | None = None) -> None:
        if not fields:
            return
        invoke("guiSelectNote", note=1)
        invoke("updateNoteFields", note={"id": self.nid, "fields": fields})
        if tags:
            tags_str = " ".join(tags)
            invoke("addTags", notes=[self.nid], tags=tags_str)
        if sessionsdb.current_session["open_in_browser"]:
            invoke("guiBrowse", query=f"nid:{self.nid}")


class AnkiContext:
    previous_notes: set[int] = set()
    last_note: AnkiNote | None = None
    curr_status: AnkiStatus = AnkiStatus.STOPPED
    start_session: datetime = datetime.now()


class AnkiSignals(QObject):
    anki_status = Signal(int)
    last_note_changed = Signal(str, str)
    note_update_info = Signal(str)
    note_update_select_line = Signal(list)
    note_update_confirm = Signal(list, object, tuple, str)

    wait_event = threading.Event()
    returned_value: Any = None

    def wait_result(self) -> Any:
        self.returned_value = None
        self.wait_event = threading.Event()
        self.wait_event.wait()
        tmp_result = self.returned_value
        self.returned_value = None
        return tmp_result

    def update_status(self, status: AnkiStatus) -> None:
        AnkiContext.curr_status = status
        self.anki_status.emit(status.value)


anki_signals = AnkiSignals()


class AnkiError(Exception):

    def __init__(self, msg: str = "") -> None:
        super().__init__()
        self.msg = msg

    def __repr__(self):
        return f"AnkiConnect: {self.msg}"


def request(action: str, **params) -> dict[str, Any]:
    return {"action": action, "params": params, "version": 6}


def invoke(action: str, **params) -> Any:
    try:
        requestJson = json.dumps(request(action, **params)).encode("utf-8")
        response = json.load(urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{AnkiSettings.port}", requestJson)))
        if len(response) != 2:  # noqa: PLR2004
            logger.error("AnkiConnect : response has an unexpected number of fields (%s, %s)", action, params)
            msg = f"response has an unexpected number of fields ({action = }, {params = })"
            raise AnkiError(msg)
        if "error" not in response:
            logger.error("AnkiConnect: response is missing required error field (%s, %s)", action, params)
            msg = f"response is missing required error field ({action = }, {params = })"
            raise AnkiError(msg)
        if "result" not in response:
            logger.error("AnkiConnect: response is missing required result field (%s, %s)", action, params)
            msg = f"response is missing required result field ({action = }, {params = })"
            raise AnkiError(msg)
        if response["error"] is not None:
            logger.error("AnkiConnect: %s (%s, %s)", response["error"], action, params)
            msg = f"{response["error"]} ({action = }, {params = })"
            raise AnkiError(msg)
        return response["result"]
    except (urllib.error.URLError, ConnectionResetError) as e:
        if AnkiContext.curr_status == AnkiStatus.CONNECTED:
            logger.error("AnkiConnect: %s (%s, %s)", e, action, params)  # noqa: TRY400
        raise AnkiError("No Connection") from e


def get_media_dir() -> str:
    return invoke("getMediaDirPath")


def get_note_types() -> list[str]:
    return invoke("modelNames")


def get_note_types_fields(name: str) -> list[str]:
    return invoke("modelFieldNames", modelName=name)


def get_all_note_types_fields(names: list[str]) -> dict[str, list[str]]:
    results = invoke("findModelsByName", modelNames=names)
    # if results is None:
    #     return None
    fields_dict: dict[str, list[str]] = {result["name"]: [field["name"] for field in result["flds"]] for result in results}
    return fields_dict


def get_last_note() -> int:
    results = invoke("findNotes", query=f"deck:{AnkiSettings.deck} added:1")
    if results:
        return max(results)
    raise AnkiError("No note found")


def get_note_info(note: int) -> dict[str, Any]:
    results = invoke("notesInfo", notes=[note])
    note_type = results[0]["modelName"]

    if note_type not in AnkiSettings.note_types:
        msg = f"noteType '{note_type}' not found in settings"
        raise AnkiError(msg)

    infos = {
        "noteType": note_type,
        "Expression": results[0]["fields"][AnkiSettings.expression[note_type]]["value"],
        "Sentence": results[0]["fields"][AnkiSettings.sentence[note_type]]["value"],
        "Picture": results[0]["fields"][AnkiSettings.picture[note_type]]["value"],
        "SentenceAudio": results[0]["fields"][AnkiSettings.sentence_audio[note_type]]["value"],
    }
    return infos


def estimate_last_interval(buffer_copy: "deque[audio.AudioInterval] | list[audio.AudioInterval]") -> tuple[int, int] | None:
    """
    Estimate timings for last voiced interval.

    Traverses buffer in reverse until last voiced interval is found,
    then keeps going until a pause in the voice is found or the 10s limit is reached.
    """
    if len(buffer_copy) == 0:
        return None

    interval_start = max(0, len(buffer_copy)-int(5/settings.audio.interval_duration))
    interval_end = len(buffer_copy) - 1
    pause_threshold = 2/settings.audio.interval_duration
    margin = 0.2

    for i in range(len(buffer_copy)-1, -1, -1):
        if buffer_copy[i].vad <= settings.audio.vad_threshold:
            continue
        interval_end = min(interval_end, i + int(margin/settings.audio.interval_duration))
        break

    pause = 0
    for i in range(interval_end-1, max(0, interval_end - int(10/settings.audio.interval_duration)), -1):
        if buffer_copy[i].vad <= settings.audio.vad_threshold:
            pause += 1
            if pause > pause_threshold:
                interval_start = max(0, i + pause - int(margin/settings.audio.interval_duration))
                break
        else:
            pause = 0

    anki_signals.note_update_confirm.emit([], buffer_copy, (interval_start, interval_end), "")
    res = anki_signals.wait_result()

    if res is None:
        return None

    _, audio_interval, _ = res
    return audio_interval


def manual_update_note(*, update_img: bool = True, update_audio: bool = True) -> None:
    if AnkiContext.last_note is None:
        anki_signals.note_update_info.emit("No note selected")
        return

    if AnkiSettings.media_dir is None:
        anki_signals.note_update_info.emit("Anki media directory not set.\n\nGo to Settings -> Anki to setup AnkiConnect.")
        return

    update_fields = {}
    curr_time = datetime.now()

    img_path = Path(AnkiSettings.media_dir) / f"{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.webp"
    audio_path = Path(AnkiSettings.media_dir) / f"{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.mp3"

    if update_img:
        screenshot._take_screenshot(curr_time, save_path=img_path)  # noqa: SLF001
        update_fields[AnkiSettings.picture[AnkiContext.last_note.noteType]] = f'<img alt="snapshot" src="{f"{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.webp"}">'

    if update_audio:
        buffer_copy = audio.buffers["primary"].copy_slice()
        audio_interval = estimate_last_interval(buffer_copy)

        if audio_interval:
            with sf.SoundFile(file=audio_path, mode="w", channels=audio.buffers["primary"].channels, samplerate=settings.audio.samplerate) as f:
                for interval in islice(buffer_copy, audio_interval[0], audio_interval[1]):
                    f.write(interval.data)
            update_fields[AnkiSettings.sentence_audio[AnkiContext.last_note.noteType]] = f"[sound:{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.mp3]"

    if update_fields:
        AnkiContext.last_note.update(update_fields)
        # update_note(AnkiContext.last_note.nid, update_fields)


def search_linesdb(sentence: str) -> dict[str, Any] | None:
    found_lines = []
    found = False

    text_copy = copy(util_sockets.text_stored)

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

def find_line_images(line_dict: dict) -> list:
    images = []
    for img in screenshot.images_tmp:
        if img.time < line_dict["line"].time:
            continue
        if line_dict["next"] and img.time > line_dict["next"].time:
            break
        images.append(img)
    return images

def note_update_confirmation(images: list, selected_line: dict, next_line_time: datetime | None = None, *, save_path: str | Path, update_audio: bool) -> tuple | None:
    buffer_copy = None
    audio_interval = None
    if update_audio:
        line_audio = audio.buffers["primary"].extract_line_audio(selected_line["line"].time, next_line_time)
        buffer_copy: deque[audio.AudioInterval] | None = line_audio[0]
        audio_interval = line_audio[1:]

    line_update = selected_line["line"].text.replace(AnkiContext.last_note.SentenceClean, AnkiContext.last_note.Sentence)  # ty:ignore[possibly-missing-attribute]

    anki_signals.note_update_confirm.emit(images, buffer_copy, audio_interval, line_update)
    res = anki_signals.wait_result()

    if res is None:
        return None

    selected_img_idx, audio_interval, line_update = res

    selected_img = images[selected_img_idx] if selected_img_idx is not None else None

    if buffer_copy and audio_interval:
        with sf.SoundFile(file=save_path, mode="w", channels=audio.buffers["primary"].channels, samplerate=settings.audio.samplerate) as f:
            for interval in islice(buffer_copy, audio_interval[0], audio_interval[1]):
                f.write(interval.data)

    return line_audio, selected_img, line_update

def auto_update_note(*, update_img: bool = True, update_audio: bool = True, confirmation: bool = False) -> None:  # noqa: C901
    if AnkiContext.last_note is None:
        anki_signals.note_update_info.emit("No note selected")
        return

    if AnkiSettings.media_dir is None:
        anki_signals.note_update_info.emit("Anki media directory not set.\n\nGo to Settings -> Anki to setup AnkiConnect.")
        return

    line_audio = (None,)
    update_fields = {}

    curr_time = datetime.now()

    if util_sockets.selected_idxs:
        selected_line = util_sockets.manual_line_selection(util_sockets.selected_idxs)
    else:
        selected_line = search_linesdb(AnkiContext.last_note.SentenceClean)

    if selected_line is None:
        return

    next_line_time = selected_line["next"].time if selected_line["next"] else None

    images = find_line_images(selected_line) if update_img else []

    img_path = Path(AnkiSettings.media_dir) / f"{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.webp"
    audio_path = Path(AnkiSettings.media_dir) / f"{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.mp3"

    if confirmation:
        res = note_update_confirmation(images, selected_line, next_line_time=next_line_time, save_path=audio_path, update_audio=update_audio)
        if res is None:
            return
        line_audio, selected_img, line_update = res
        update_fields[AnkiSettings.sentence[AnkiContext.last_note.noteType]] = line_update
    else:
        if update_audio:
            line_audio = audio.buffers["primary"].extract_line_audio(selected_line["line"].time, next_line_time, save_path=audio_path)

        selected_img = images[0] if images else None

        if selected_line["line"].text != AnkiContext.last_note.SentenceClean:
            line_update = selected_line["line"].text.replace(AnkiContext.last_note.SentenceClean, AnkiContext.last_note.Sentence)
            update_fields[AnkiSettings.sentence[AnkiContext.last_note.noteType]] = line_update

    if selected_img:
        with open(img_path, "wb") as f:
            f.write(selected_img.img_bytesIO.getbuffer())
        update_fields[AnkiSettings.picture[AnkiContext.last_note.noteType]] = f'<img alt="snapshot" src="{f"{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.webp"}">'

    if line_audio[0]:
        update_fields[AnkiSettings.sentence_audio[AnkiContext.last_note.noteType]] = f"[sound:{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.mp3]"

    AnkiContext.last_note.update(update_fields)
    # update_note(AnkiContext.last_note.nid, update_fields)


def monitor_last_note(widget_info_update=None):
    first_fail = True
    while True:
        try:
            if AnkiContext.curr_status != AnkiStatus.CONNECTED:
                continue

            last_note_tmp = get_last_note()

            if last_note_tmp == AnkiContext.last_note:
                continue

            last_note_info = get_note_info(last_note_tmp)

            AnkiContext.last_note = AnkiNote(nid=last_note_tmp, info=last_note_info)
            anki_signals.last_note_changed.emit(last_note_info["Expression"], AnkiContext.last_note.SentenceClean)

            if last_note_tmp not in AnkiContext.previous_notes:
                AnkiContext.previous_notes.add(last_note_tmp)
                if sessionsdb.current_session["auto_update"] and AnkiContext.last_note.nid > AnkiContext.start_session.timestamp()*1000:
                    auto_update_note(confirmation=sessionsdb.current_session["preview_note"])
        except AnkiError:
            if AnkiContext.last_note is not None or first_fail:
                first_fail = False
                logger.info("No note found")
                AnkiContext.last_note = None
                anki_signals.last_note_changed.emit("No note found", "")
        except Exception as e:
            # logger.warning("monitor_last_note: %s", e)
            logger.exception("monitor_last_note: ")
        finally:
            sleep(0.2)


def check_anki_status():
    logger.info("Start monitotoring Anki connection")
    while True:
        try:
            requestJson = json.dumps(request("version")).encode("utf-8")
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{AnkiSettings.port}", requestJson))
        except (urllib.error.URLError, ConnectionResetError) as e:
            if AnkiContext.curr_status != AnkiStatus.STARTED:
                msg = f"AnkiConnect: {e}"
                logger.error(msg)  # noqa: TRY400
                anki_signals.update_status(AnkiStatus.STARTED)
        except Exception:
            logger.exception("AnkiConnect: ")
            anki_signals.update_status(AnkiStatus.STOPPED)
            break
        else:
            if AnkiContext.curr_status != AnkiStatus.CONNECTED:
                logger.info("AnkiConnect: connected")
                anki_signals.update_status(AnkiStatus.CONNECTED)
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
