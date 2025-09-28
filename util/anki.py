import os
import re
import json
import urllib.request
import threading
from time import sleep
from datetime import datetime
from copy import copy
import traceback

import util.sockets
# import util.util as util
import util.audio as audio
import util.screenshot as screenshot

anki_port = 8765
previous_notes = set()
last_note = None
last_note_update_time = None
last_note_info = None
last_note_sentence_clean = None
auto_update = True
open_add_note_in_gui = True

card_fields = {"Expression": "Expression",
               "Sentence": "Sentence"}


def request(action, **params):
    return {'action': action, 'params': params, 'version': 6}


def invoke(action, **params):
    requestJson = json.dumps(request(action, **params)).encode('utf-8')
    response = json.load(urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{anki_port}', requestJson)))
    if len(response) != 2:
        raise Exception('response has an unexpected number of fields')
    if 'error' not in response:
        raise Exception('response is missing required error field')
    if 'result' not in response:
        raise Exception('response is missing required result field')
    if response['error'] is not None:
        raise Exception(response['error'])
    return response['result']


def get_media_dir():
    results = invoke("getMediaDirPath")
    return results


def get_last_note():
    results = invoke("findNotes", query="deck:Mining added:1")
    if results:
        return max(results)
    else:
        # return -1
        raise Exception("No note added today")


def get_note_info(note):
    results = invoke("notesInfo", notes=[note])
    infos = {field: results[0]["fields"][field]["value"] for field in card_fields.values()}
    return infos


def update_note(note_id, fields, tags=""):
    invoke("guiSelectNote", note=1)
    invoke("updateNoteFields", note={"id": note_id, "fields": fields})
    if tags:
        invoke("addTags", notes=[note_id], tags=tags)
    if open_add_note_in_gui:
        invoke("guiBrowse", query=f"nid:{note_id}")


media_dir = None
start_session = datetime.now()


def auto_update_note():
    global media_dir
    found_lines = []
    substring_idx = None
    # next_line = util.sockets.LineStored(text=None, time=None)
    images = []
    line_audio = None
    line_update = None
    found = False

    text_copy = copy(util.sockets.text_stored)

    print(f"last_note_sentence_clean: {last_note_sentence_clean}")

    for line in text_copy:

        if found:
            # next_line = line
            # break
            found_lines[-1]["next"] = line
            found = False

        print(f"line.text: {line.text}")

        substring_idx = line.text.find(last_note_sentence_clean)

        print(f"substring_idx: {substring_idx}")

        if substring_idx == -1:
            continue
        else:
            found_lines.append({"line": line, "next": None, "substring_idx": substring_idx})
            found = True

    if not found_lines:
        return

    if len(found_lines) > 1:
        print("more then one sentence matched")
        return

    for img in screenshot.images_tmp:
        if img.time < found_lines[0]["line"].time:
            continue
        if found_lines[0]["next"] and img.time > found_lines[0]["next"].time:
            continue
        images.append(img)

    if media_dir is None:
        media_dir = get_media_dir()

    curr_time = datetime.now()

    audio_path = os.path.join(media_dir, f"{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.mp3")
    img_path = os.path.join(media_dir, f"{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.webp")

    line_audio = audio.buffer.extract_line_audio(found_lines[0]["line"].time, found_lines[0]["next"].time, save_on_disk=True, save_path=audio_path)

    update_fields = {}

    if found_lines[0]["line"].text != last_note_sentence_clean:
        line_update = found_lines[0]["line"].text.replace(last_note_sentence_clean, last_note_info[card_fields["Sentence"]])

    if line_update:
        update_fields["Sentence"] = line_update

    if images:
        with open(img_path, "wb") as f:
            f.write(images[0].img_bytesIO.getbuffer())
        update_fields["Picture"] = f'<img alt="snapshot" src="{f"{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.webp"}">'

    if line_audio:
        update_fields["SentenceAudio"] = f"[sound:{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.mp3]"

    if update_fields:
        update_note(last_note, update_fields)


CLEANER = re.compile('<.*?>')


def cleanhtml(raw_html):
    cleantext = re.sub(CLEANER, '', raw_html)
    return cleantext


def monitor_last_note(widget_info_update=None):
    global last_note, last_note_update_time, last_note_info, last_note_sentence_clean
    while True:
        try:
            last_note_tmp = get_last_note()
            if last_note_tmp not in previous_notes:
                previous_notes.add(last_note_tmp)
                last_note = last_note_tmp
                last_note_update_time = datetime.now()
                last_note_info = get_note_info(last_note)
                last_note_sentence_clean = cleanhtml(last_note_info[card_fields["Sentence"]])
                if widget_info_update:
                    widget_info_update(f"Word: {last_note_info[card_fields["Expression"]]}\nSentence: {last_note_sentence_clean}")
                print(f"last_note: {last_note}, start_session.timestamp(): {start_session.timestamp()*1000}")
                if auto_update and last_note > start_session.timestamp()*1000:
                    auto_update_note()
        except Exception as e:
            if "No note added today" in str(e):
                if last_note != -1:
                    print("No note added today")
                    last_note = -1
                    widget_info_update("Word:\nSentence:")
            else:
                traceback.print_exc()
        finally:
            sleep(0.2)


def start_monitoring_anki(widget_info_update=None):
    anki_thread = threading.Thread(target=monitor_last_note, args=[widget_info_update], daemon=True)
    anki_thread.start()
