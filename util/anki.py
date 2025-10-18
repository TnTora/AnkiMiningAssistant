import os
import re
import json
import urllib.request
import urllib.error
import threading
from time import sleep
from datetime import datetime
from copy import copy
import traceback

from PySide6.QtCore import QObject, Signal

import util.sockets
import util.audio as audio
import util.screenshot as screenshot
from util.database import AnkiSettings, settings, sessionsdb

previous_notes = set()
last_note = None
last_note_update_time = None
last_note_info = None
last_note_sentence_clean = None

start_session = datetime.now()


class AnkiSignals(QObject):
    anki_status = Signal(int)


anki_signals = AnkiSignals()


def request(action, **params):
    return {'action': action, 'params': params, 'version': 6}


def invoke(action, **params):
    try:
        requestJson = json.dumps(request(action, **params)).encode('utf-8')
        response = json.load(urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{AnkiSettings.port}', requestJson)))
        if len(response) != 2:
            raise Exception('response has an unexpected number of fields')
        if 'error' not in response:
            raise Exception('response is missing required error field')
        if 'result' not in response:
            raise Exception('response is missing required result field')
        if response['error'] is not None:
            raise Exception(response['error'])
        return response['result']
    except Exception:
        # traceback.print_exc()
        return


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
    else:
        # return -1
        raise Exception("No note found")


def get_note_info(note):
    results = invoke("notesInfo", notes=[note])
    note_type = results[0]["modelName"]

    if note_type not in AnkiSettings.note_types:
        return

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


def auto_update_note(update_img: bool = True, update_audio: bool = True) -> None:
    if last_note is None:
        # TODO: Inform user update failed
        return

    found_lines = []
    next_line_time = None
    substring_idx = None
    images = []
    line_audio = None
    line_update = None
    found = False

    text_copy = copy(util.sockets.text_stored)
    curr_time = datetime.now()

    if AnkiSettings.media_dir is None:
        media_dir = get_media_dir()
        if media_dir is None:
            return
        settings.update_option("anki", "media_dir", media_dir)

    for line in text_copy:

        if found:
            found_lines[-1]["next"] = line
            found = False

        substring_idx = line.text.find(last_note_sentence_clean)

        if substring_idx == -1:
            continue
        else:
            found_lines.append({"line": line, "next": None, "substring_idx": substring_idx})
            found = True

    if not found_lines:
        # TODO: Inform user that no match was found
        return

    if len(found_lines) > 1:
        print("more then one sentence matched")
        # TODO: Open dialog window to allow user to select a sinle line
        return

    if found_lines[0]["next"]:
        next_line_time = found_lines[0]["next"].time

    if update_img:
        for img in screenshot.images_tmp:
            if img.time < found_lines[0]["line"].time:
                continue
            if found_lines[0]["next"] and img.time > found_lines[0]["next"].time:
                break
            images.append(img)

    img_path = os.path.join(AnkiSettings.media_dir, f"{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.webp")
    audio_path = os.path.join(AnkiSettings.media_dir, f"{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.mp3")

    if update_audio:
        line_audio = audio.buffer.extract_line_audio(found_lines[0]["line"].time, next_line_time, save_path=audio_path)

    update_fields = {}

    if found_lines[0]["line"].text != last_note_sentence_clean:
        line_update = found_lines[0]["line"].text.replace(last_note_sentence_clean, last_note_info["Sentence"])
        update_fields[AnkiSettings.sentence[last_note_info["noteType"]]] = line_update

    if images:
        with open(img_path, "wb") as f:
            f.write(images[0].img_bytesIO.getbuffer())
        update_fields[AnkiSettings.picture[last_note_info["noteType"]]] = f'<img alt="snapshot" src="{f"{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.webp"}">'

    if line_audio:
        update_fields[AnkiSettings.sentence_audio[last_note_info["noteType"]]] = f"[sound:{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.mp3]"

    if update_fields:
        update_note(last_note, update_fields)


CLEANER = re.compile('<.*?>')


def cleanhtml(raw_html):
    cleantext = re.sub(CLEANER, '', raw_html)
    return cleantext


def monitor_last_note(widget_info_update=None):
    global last_note, last_note_update_time, last_note_info, last_note_sentence_clean
    first_fail = True
    while True:
        try:
            last_note_tmp = get_last_note()

            if last_note_tmp not in previous_notes:

                last_note = last_note_tmp
                last_note_update_time = datetime.now()
                last_note_info = get_note_info(last_note)

                if last_note_info is None:
                    continue

                last_note_sentence_clean = cleanhtml(last_note_info["Sentence"])
                previous_notes.add(last_note_tmp)

                if widget_info_update:
                    widget_info_update(last_note_info["Expression"], last_note_sentence_clean)

                if sessionsdb.current_session["auto_update"] and last_note > start_session.timestamp()*1000:
                    auto_update_note()

        except Exception as e:
            if "No note found" in str(e):
                if last_note is not None or first_fail:
                    first_fail = False
                    print("No note found")
                    last_note = None
                    widget_info_update("", "")
            else:
                traceback.print_exc()
        finally:
            sleep(0.2)


def check_anki_status():
    while True:
        try:
            requestJson = json.dumps(request("version")).encode('utf-8')
            urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{AnkiSettings.port}', requestJson))
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


def start_auto_note_update(update_img, update_audio):
    update_thread = threading.Thread(
        target=auto_update_note,
        kwargs={"update_img": update_img, "update_audio": update_audio},
        daemon=True
    )
    update_thread.start()
    return update_thread
