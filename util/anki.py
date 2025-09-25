import re
import json
import urllib.request
import threading
from time import time, sleep

anki_port = 8765
previous_notes = set()
last_note = None
last_note_update_time = None
last_note_info = None
last_note_sentence_clean = None
auto_update = True

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
    invoke("guiBrowse", query=f"nid:{note_id}")


CLEANR = re.compile('<.*?>')


def cleanhtml(raw_html):
    cleantext = re.sub(CLEANR, '', raw_html)
    return cleantext


def monitor_last_note(widget_info_update=None):
    global last_note, last_note_update_time, last_note_info, last_note_sentence_clean
    while True:
        try:
            last_note_tmp = get_last_note()
            if last_note_tmp not in previous_notes:
                last_note = last_note_tmp
                last_note_update_time = time()
                last_note_info = get_note_info(last_note)
                last_note_sentence_clean = cleanhtml(last_note_info[card_fields["Sentence"]])
                if widget_info_update:
                    widget_info_update(f"Word: {last_note_info[card_fields["Expression"]]}\nSentence: {last_note_sentence_clean}")
                if auto_update:
                    pass
        except Exception as e:
            if "No note added today" in str(e) and last_note is not None:
                last_note = None
                widget_info_update("Word:\nSentence:")
            pass
        finally:
            sleep(0.2)


def start_monitoring_anki(widget_info_update=None):
    anki_thread = threading.Thread(target=monitor_last_note, args=[widget_info_update], daemon=True)
    anki_thread.start()
