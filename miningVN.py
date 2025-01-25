import json
import urllib.request
import shlex
import subprocess
from datetime import datetime
from time import sleep


def request(action, **params):
    return {'action': action, 'params': params, 'version': 6}


def invoke(action, **params):
    requestJson = json.dumps(request(action, **params)).encode('utf-8')
    response = json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8765', requestJson)))
    if len(response) != 2:
        raise Exception('response has an unexpected number of fields')
    if 'error' not in response:
        raise Exception('response is missing required error field')
    if 'result' not in response:
        raise Exception('response is missing required result field')
    if response['error'] is not None:
        raise Exception(response['error'])
    return response['result']


def get_last_note():
    results = invoke("findNotes", query="deck:Mining added:1")
    if results:
        return max(results)
    else:
        # return -1
        raise Exception("No note added today")


def update_note(note_id, fields, tags=""):
    invoke("guiSelectNote", note=1)
    invoke("updateNoteFields", note={"id": note_id, "fields": fields})
    if tags:
        invoke("addTags", notes=[note_id], tags=tags)
    invoke("guiBrowse", query=f"nid:{note_id}")


def record(session, audio=False, screenshot=False, tags=""):
    curr_time = datetime.now()
    last_note = get_last_note()
    update_fields = {}

    note_time = datetime.fromtimestamp(last_note/1000)
    diff = (curr_time - note_time).seconds
    if diff > 5*60:
        while True:
            go_ahead = str(input("Last note was added over 5 minutes ago. Are you sure it is the one you want to update (y/n): ")).strip()
            if go_ahead == "y":
                break
            elif go_ahead == "n":
                return
            else:
                print("Invalid choice")

    curr_time = curr_time.strftime('%Y-%m-%d_%H_%M_%S')

    if screenshot:
        try:
            subprocess.run(shlex.split(f"screencapture -o -i -J window '/Users/ludo/Library/Application Support/Anki2/User 1/collection.media/VN-{session}_{curr_time}.jpg'"))
            subprocess.run(shlex.split(f"ffmpeg -i '/Users/ludo/Library/Application Support/Anki2/User 1/collection.media/VN-{session}_{curr_time}.jpg' '/Users/ludo/Library/Application Support/Anki2/User 1/collection.media/VN-{session}_{curr_time}.webp'"))
            subprocess.run(shlex.split(f"rm '/Users/ludo/Library/Application Support/Anki2/User 1/collection.media/VN-{session}_{curr_time}.jpg'"))

            update_fields["Picture"] = f'<img alt="snapshot" src="VN-{session}_{curr_time}.webp">'
        except KeyboardInterrupt:
            pass

    if audio:
        print("Starting recording in...")
        for i in range(2, 0, -1):
            print(i)
            sleep(1)
        print("Recording...")

        try:
            subprocess.run(shlex.split(f"sox -t coreaudio 'BlackHole 2ch' '/Users/ludo/Library/Application Support/Anki2/User 1/collection.media/VN-{session}_{curr_time}.mp3'"))
        except KeyboardInterrupt:
            update_fields["SentenceAudio"] = f"[sound:VN-{session}_{curr_time}.mp3]"

    # if last_note > 0:
    if update_fields:
        update_note(last_note, update_fields, tags)


input("Make sure audio output device and terminal permission are set up correctly then press ENTER")

session_name = input("Write session name: ")
while True:
    type_selection = str(input("[1] Screenshot\n[2] Audio\n[3] Both\n[q] Quit\nChoose: ")).strip()
    tag = "VN "+session_name.replace(" ", "_")
    if type_selection[-1] == "N":
        tag += "NSFW "
        type_selection = type_selection[0]
    if type_selection == "2":
        record(session_name, audio=True, tags=tag)
    elif type_selection == "1":
        record(session_name, screenshot=True, tags=tag)
    elif type_selection == "3":
        record(session_name, audio=True, screenshot=True, tags=tag)
    elif type_selection == "q":
        break
    else:
        print("innvalid choice")
