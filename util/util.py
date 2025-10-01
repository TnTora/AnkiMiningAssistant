import json
import threading
import tempfile
import os
# import sys
import numpy as np
# import soundcard as sc
import soundfile as sf
# import pywinctl as pwc
from datetime import datetime
from time import sleep

from PySide6.QtCore import Signal, QObject

from util.anki import last_note_update_time, get_last_note, get_media_dir, update_note


from util.audio import recordAudio, SAMPLERATE
from util.screenshot import take_screenshot
from util.database import AnkiSettings

from pynput import keyboard


hotkeys_enabled = True
recording = None


def recordHotKeyBoth(data=None):
    if recording is not None:
        recording.set()
    if hotkeys_enabled:
        thread = threading.Thread(
            target=record,
            args=(session_name,),
            kwargs={"audio": True, "screenshot": True, "tags": tag, "audio_data": data})
        thread.start()
        # record(session_name, audio=True, screenshot=True, tags=tag)


def recordHotKeyAudio(data=None):
    if recording is not None:
        recording.set()
    if hotkeys_enabled:
        thread = threading.Thread(
            target=record,
            args=(session_name,),
            kwargs={"audio": True, "tags": tag, "audio_data": data})
        thread.start()
        # record(session_name, audio=True, tags=tag)


def recordHotKeyScreenshot():
    if hotkeys_enabled:
        thread = threading.Thread(
            target=record,
            args=(session_name,),
            kwargs={"screenshot": True, "tags": tag})
        thread.start()
        # record(session_name, screenshot=True, tags=tag)


hotkeys = keyboard.GlobalHotKeys({
    '<alt>+p': recordHotKeyAudio,
    '<alt>+0': recordHotKeyScreenshot,
    '<alt>+o': recordHotKeyBoth,
})


# confirm = Signal(str)
confirmed = None


class Signals(QObject):
    confirm = Signal(str)


signals = Signals()
condition = threading.Event()


def record(session, audio=False, screenshot=False, audio_data=None, tags=""):
    global hotkeys_enabled, confirmed, last_note
    hotkeys_enabled = False
    curr_time = datetime.now()

    if curr_time.timestamp() - last_note_update_time < 0.2:
        try:
            last_note = get_last_note()
        except Exception as e:
            print(e)
            return

    if AnkiSettings.media_dir is None:
        media_dir = get_media_dir()
        if media_dir is None:
            return
        AnkiSettings.media_dir = media_dir

    update_fields = {}

    note_time = datetime.fromtimestamp(last_note/1000)
    diff = (curr_time - note_time).minutes

    if diff > 5:
        signals.confirm.emit("Last note was added over 5 minutes ago. Are you sure it is the one you want to update?")
        condition.wait()

        if confirmed:
            # print("yes")
            pass
        else:
            # print("no")
            hotkeys_enabled = True
            return

    curr_time_str = curr_time.strftime('%Y-%m-%d_%H_%M_%S')

    if screenshot:

        take_screenshot()
        update_fields["Picture"] = f'<img alt="snapshot" src="{curr_time_str}.webp">'

    if audio_data:
        # print(audio_data)
        # print(np.concatenate(audio_data))
        sf.write(
            file=os.path.join(AnkiSettings.media_dir, f"{session}_{curr_time_str}.mp3"),
            data=np.concatenate(audio_data),
            samplerate=SAMPLERATE
        )
        update_fields["SentenceAudio"] = f"[sound:{session}_{curr_time_str}.mp3]"
    elif audio:

        print("Starting recording in...")
        for i in range(2, 0, -1):
            print(i)
            sleep(1)

        print("Recording...")
        recordAudio(os.path.join(AnkiSettings.media_dir, f"{session}_{curr_time_str}.mp3"))

        update_fields["SentenceAudio"] = f"[sound:{session}_{curr_time_str}.mp3]"

    # if last_note > 0:
    if update_fields:
        update_note(last_note, update_fields, tags)

    hotkeys_enabled = True


def updateSessions():
    with open(os.path.join(directory, "sessions.json"), "w") as f:
        json.dump(sessions, f, indent=4)


directory = os.path.split(os.path.realpath(__file__))[0]

if not os.path.isfile(os.path.join(directory, "sessions.json")):
    with open(os.path.join(directory, "sessions.json"), "w") as f:
        json.dump({}, f)

with open(os.path.join(directory, "sessions.json")) as f:
    try:
        sessions = json.load(f)
    except ValueError:
        sessions = {}


temp_dir = tempfile.TemporaryDirectory()
# print(temp_dir.name)
# use temp_dir, and when done:
# temp_dir.cleanup()

# try:
#     media_dir = get_media_dir()
# except Exception as e:
#     media_dir = None
#     print(f"Failed to get Anki media directory.\n{e}")

# sessions = {
#     "SessionName": {
#         "AppName": "app.localizedName()",
#         "WindowTitle": "kCGWindowName"
#     }
# }

# session = None
session_name = None
button = None

# se = getAS_SystemEvents()
app = None
# proc = None
# selected_win_AX = None
win = None

use_button = False
tag = ""
