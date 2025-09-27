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
from time import sleep, time
from PIL import ImageGrab  # , Image

# import torch
# import torchaudio
# from silero_vad import load_silero_vad

from PySide6.QtCore import Signal, QObject

# from util.AggregateDevice import isloopback
from util.anki import last_note_update_time, get_last_note, get_media_dir, update_note
from util.mac import (
    isCurrentlyActive,
    activateWindow,
    getAXWindowBounds,
    getAS_SystemEvents,
)
# from util.sockets import WebsocketManagerThread
from util.audio import recordAudio, SAMPLERATE

from pynput import mouse, keyboard  # noqa

mouse_controller = mouse.Controller()
targetX = None
targetY = None


def on_click(x, y, button, pressed):
    global targetX, targetY
    if pressed and button == mouse.Button.left:
        print(f"button: {button}, ({x}, {y})")
        targetX = x
        targetY = y
    else:
        # Stop listener
        return False


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
    global hotkeys_enabled, media_dir, confirmed, last_note
    hotkeys_enabled = False
    curr_time = datetime.now()

    if curr_time.timestamp() - last_note_update_time < 0.2:
        try:
            last_note = get_last_note()
        except Exception as e:
            print(e)
            return

    if media_dir is None:
        media_dir = get_media_dir()

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
    bounds = getAXWindowBounds(selected_win_AX)

    if screenshot:
        try:
            if not isCurrentlyActive(app):
                activateWindow(app, proc, selected_win_AX)

            st = time()
            rect = (int(bounds["X"]), int(bounds["Y"]), int(bounds["X"]+bounds["Width"]), int(bounds["Y"]+bounds["Height"]))
            im = ImageGrab.grab(bbox=rect)
            fin = time()
            # im = ImageGrab.grab(bbox=selected_win.rect)

            print(f"took {fin-st}s)")

            im.save(os.path.join(media_dir, f"{session}_{curr_time_str}.webp"))

            update_fields["Picture"] = f'<img alt="snapshot" src="{session}_{curr_time_str}.webp">'
        except KeyboardInterrupt:
            pass

    if audio_data:
        # print(audio_data)
        # print(np.concatenate(audio_data))
        sf.write(
            file=os.path.join(media_dir, f"VN-{session}_{curr_time}.mp3"),
            data=np.concatenate(audio_data),
            samplerate=SAMPLERATE
        )
        update_fields["SentenceAudio"] = f"[sound:VN-{session}_{curr_time}.mp3]"
    elif audio:
        # app.activateWithOptions_(Quartz.NSApplicationActivateIgnoringOtherApps)
        # selected_win.activate()
        if not isCurrentlyActive(app):
            activateWindow(app, proc, selected_win_AX)
        if use_button and isCurrentlyActive(app):
            thread = threading.Thread(
                target=recordAudio,
                args=(os.path.join(media_dir, f"VN-{session}_{curr_time}.mp3"),))
            mouse_controller.position = (
                bounds["X"]+(button["x_rel"]*bounds["Width"]),
                bounds["Y"]+(button["y_rel"]*bounds["Height"])
            )
            sleep(0.1)
            thread.start()
            mouse_controller.click(mouse.Button.left, 1)
            thread.join()
        else:
            print("Starting recording in...")
            for i in range(2, 0, -1):
                print(i)
                sleep(1)

            print("Recording...")
            recordAudio(os.path.join(media_dir, f"VN-{session}_{curr_time}.mp3"))

        update_fields["SentenceAudio"] = f"[sound:VN-{session}_{curr_time}.mp3]"

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

try:
    media_dir = get_media_dir()
except Exception as e:
    media_dir = None
    print(f"Failed to get Anki media directory.\n{e}")

# sessions = {
#     "SessionName": {
#         "AppName": "app.localizedName()",
#         "WindowTitle": "kCGWindowName"
#     }
# }

session = None
session_name = None
button = None

se = getAS_SystemEvents()
app = None
proc = None
selected_win_AX = None
win = None

use_button = False
tag = ""

# ws_server = WebsocketManagerThread(ws_port=6678, listen_urls=["localhost:6677"])
# ws_server.start()
