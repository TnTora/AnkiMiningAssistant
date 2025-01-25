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


def record_audio(session, tags=""):
    curr_time = datetime.now()
    last_note = get_last_note()

    note_time = datetime.fromtimestamp(last_note/1000)
    diff = (curr_time - note_time).seconds
    if diff > 2*60:
        while True:
            go_ahead = str(input("Last note was added over 2 minutes ago. Are you sure it is the one you want to update (y/n): ")).strip()
            if go_ahead == "y":
                break
            elif go_ahead == "n":
                return
            else:
                print("Invalid choice")

    curr_time = curr_time.strftime('%Y-%m-%d_%H_%M_%S')

    print("Starting recording in...")
    print(2)
    sleep(1)
    print(1)
    sleep(1)
    print("Recording...")
    try:
        subprocess.run(shlex.split(f"sox -t coreaudio 'BlackHole 2ch' '/Users/ludo/Library/Application Support/Anki2/User 1/collection.media/VN-{session}_{curr_time}.mp3'"))
    except KeyboardInterrupt:
        pass

    # last_note = get_last_note()
    # if last_note > 0:
    update_note(last_note, {"SentenceAudio": f"[sound:VN-{session}_{curr_time}.mp3]"}, tags)


def screenshot(session, tags=""):
    curr_time = datetime.now()
    last_note = get_last_note()

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
    try:
        subprocess.run(shlex.split(f"screencapture -o -i -J window '/Users/ludo/Library/Application Support/Anki2/User 1/collection.media/VN-{session}_{curr_time}.jpg'"))
        subprocess.run(shlex.split(f"ffmpeg -i '/Users/ludo/Library/Application Support/Anki2/User 1/collection.media/VN-{session}_{curr_time}.jpg' '/Users/ludo/Library/Application Support/Anki2/User 1/collection.media/VN-{session}_{curr_time}.webp'"))
        subprocess.run(shlex.split(f"rm '/Users/ludo/Library/Application Support/Anki2/User 1/collection.media/VN-{session}_{curr_time}.jpg'"))
    except KeyboardInterrupt:
        pass

    # last_note = get_last_note()
    # if last_note > 0:
    update_note(last_note, {"Picture": f'<img alt="snapshot" src="VN-{session}_{curr_time}.webp">'}, tags)


def both(session, tags=""):
    curr_time = datetime.now()
    last_note = get_last_note()

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
    try:
        subprocess.run(shlex.split(f"screencapture -o -i -J window '/Users/ludo/Library/Application Support/Anki2/User 1/collection.media/VN-{session}_{curr_time}.jpg'"))
        subprocess.run(shlex.split(f"ffmpeg -i '/Users/ludo/Library/Application Support/Anki2/User 1/collection.media/VN-{session}_{curr_time}.jpg' '/Users/ludo/Library/Application Support/Anki2/User 1/collection.media/VN-{session}_{curr_time}.webp'"))
        subprocess.run(shlex.split(f"rm '/Users/ludo/Library/Application Support/Anki2/User 1/collection.media/VN-{session}_{curr_time}.jpg'"))
    except KeyboardInterrupt:
        pass

    print("Starting recording in...")
    print(2)
    sleep(1)
    print(1)
    sleep(1)
    print("Recording...")

    try:
        subprocess.run(shlex.split(f"sox -t coreaudio 'BlackHole 2ch' '/Users/ludo/Library/Application Support/Anki2/User 1/collection.media/VN-{session}_{curr_time}.mp3'"))
    except KeyboardInterrupt:
        pass

    # if last_note > 0:
    update_note(last_note, {"SentenceAudio": f"[sound:VN-{session}_{curr_time}.mp3]", "Picture": f'<img alt="snapshot" src="VN-{session}_{curr_time}.webp">'}, tags)


input("Make sure audio output device and terminal permission are set up correctly then press ENTER")

session_name = input("Write session name: ")
while True:
    type_selection = str(input("[1] Screenshot\n[2] Audio\n[3] Both\nChoose: ")).strip()
    tag = "VN "+session_name.replace(" ", "_")
    if type_selection[-1] == "N":
        tag += "NSFW "
        type_selection = type_selection[0]
    if type_selection == "2":
        record_audio(session_name, tags=tag)
    elif type_selection == "1":
        screenshot(session_name, tags=tag)
    elif type_selection == "3":
        both(session_name, tags=tag)
    else:
        print("innvalid choice")
