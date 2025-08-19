import json
import urllib.request
import threading
# import shlex
# import subprocess
import os
# import sys
import numpy as np
import soundcard as sc
import soundfile as sf
# import pywinctl as pwc
from datetime import datetime
from time import sleep, time
from PIL import ImageGrab  # , Image

import torch
import torchaudio
from silero_vad import load_silero_vad

import AppKit
import Quartz
from Foundation import NSRunLoop, NSDefaultRunLoopMode, NSPredicate
import ApplicationServices
import ScriptingBridge

from AggregateDevice import isloopback

"""
Bridging to undocumented private API to get CGWindowID from AXUIElement Window

    AXError _AXUIElementGetWindow(AXUIElementRef, CGWindowID* out);

usage:
err, winID = _AXUIElementGetWindow(window, None)
"""

import objc
bundle = objc.loadBundle("ApplicationServices", bundle_path="/System/Library/Frameworks/ApplicationServices.framework", module_globals=globals())
functions = [("_AXUIElementGetWindow", objc._C_INT+b'^{__AXUIElement=}'+objc._C_OUT+objc._C_PTR+objc._C_UINT)]
try:
    objc.loadBundleFunctions(bundle, globals(), functions, skip_undefined=False)
    usePrivateAPI = True
except objc.error as e:
    usePrivateAPI = False
    print(e)


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
monitoringAudio = None


def recordHotKeyBoth():
    if recording is not None:
        recording.set()
    if hotkeys_enabled:
        thread = threading.Thread(
            target=record,
            args=(session_name,),
            kwargs={"audio": True, "screenshot": True, "tags": tag})
        thread.start()
        # record(session_name, audio=True, screenshot=True, tags=tag)


def recordHotKeyAudio():
    if recording is not None:
        recording.set()
    if hotkeys_enabled:
        thread = threading.Thread(
            target=record,
            args=(session_name,),
            kwargs={"audio": True, "tags": tag})
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

app_info = AppKit.NSBundle.mainBundle().infoDictionary()
app_info["LSBackgroundOnly"] = "1"  # used to suppress python macOS dock icon pop up/bounce


runLoop = NSRunLoop.currentRunLoop()


def getAllApps():
    matches = []
    # The list only get updated when the loop runs, so we call it for a single cycle
    runLoop.limitDateForMode_(NSDefaultRunLoopMode)
    for app in AppKit.NSWorkspace.sharedWorkspace().runningApplications():
        if app.activationPolicy() == Quartz.NSApplicationActivationPolicyRegular:
            matches.append(app)
    return matches


def getAppWindows(app):

    def conditions(x):
        try:
            if x["kCGWindowOwnerPID"] != app.processIdentifier():
                return False
            if x["kCGWindowLayer"] > 0:
                return False
            bounds = x["kCGWindowBounds"]
            if bounds["Y"] == 0:
                return False
            if bounds["Height"] == 0 or bounds["Width"] == 0:
                return False
            title = x["kCGWindowName"]
            if title:
                return True
            else:
                return False
        except KeyError:
            return False

    matches = []
    for win in Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListExcludeDesktopElements | Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID):
        if conditions(win):
            matches.append(win)
    return matches


def getAppAXWindows(app):
    ax_test = ApplicationServices.AXUIElementCreateApplication(app.processIdentifier())
    win_test = ApplicationServices.AXUIElementCopyAttributeValues(ax_test, ApplicationServices.kAXWindowsAttribute, 0, 99999, None)[1]
    return win_test


def getAXWindowBounds(ax_win):
    pos = ApplicationServices.AXUIElementCopyAttributeValue(ax_win, ApplicationServices.kAXPositionAttribute, None)[1]
    if pos is None:
        return
    pos_value = ApplicationServices.AXValueGetValue(pos, ApplicationServices.kAXValueCGPointType, None)[1]
    size = ApplicationServices.AXUIElementCopyAttributeValue(ax_win, ApplicationServices.kAXSizeAttribute, None)[1]
    if size is None:
        return
    size_value = ApplicationServices.AXValueGetValue(size, ApplicationServices.kAXValueCGSizeType, None)[1]
    bounds = {
        "Height": int(size_value.height),
        "Width": int(size_value.width),
        "X": int(pos_value.x),
        "Y": int(pos_value.y),
    }
    return bounds


def getAXWindowFromWindowInfo(AXWindowsList, win):
    for ax_win in AXWindowsList:
        if usePrivateAPI:
            err, winID = _AXUIElementGetWindow(ax_win, None)  # noqa
            if win["kCGWindowNumber"] == winID:
                print("AXWindow found by private API")
                return ax_win

        title = ApplicationServices.AXUIElementCopyAttributeValue(ax_win, ApplicationServices.kAXTitleAttribute, None)[1]
        if title is None:
            continue

        bounds = getAXWindowBounds(ax_win)

        if win["kCGWindowName"] != title:
            continue
        if win["kCGWindowBounds"] != bounds:
            continue

        return ax_win


def activateWindow(app, proc, win_ax):
    app.activateWithOptions_(Quartz.NSApplicationActivateIgnoringOtherApps)
    ApplicationServices.AXUIElementPerformAction(win_ax, ApplicationServices.kAXRaiseAction)
    # print(f"isCurrentlyActive: {isCurrentlyActive(app)}")
    sleep(0.1)
    # print(f"isCurrentlyActive: {isCurrentlyActive(app)}")
    if not isCurrentlyActive(app):
        proc.setFrontmost_(True)


def isCurrentlyActive(app):
    activeAppName = AppKit.NSWorkspace.sharedWorkspace().activeApplication()["NSWorkspaceApplicationKey"]
    return app == activeAppName


def getAS_SystemEvents():
    return ScriptingBridge.SBApplication.applicationWithBundleIdentifier_("com.apple.systemevents")


def getAS_Process(se, app):
    processes = se.processes()
    pred = NSPredicate.predicateWithFormat_(f"unixId == {app.processIdentifier()}")
    return processes.filteredArrayUsingPredicate_(pred)[0]


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


def update_note(note_id, fields, tags=""):
    invoke("guiSelectNote", note=1)
    invoke("updateNoteFields", note={"id": note_id, "fields": fields})
    if tags:
        invoke("addTags", notes=[note_id], tags=tags)
    invoke("guiBrowse", query=f"nid:{note_id}")


def recordAudio(filepath):
    global recording
    SAMPLERATE = 44100
    INTERVAL_DURATION = 0.1
    data = None
    try:
        recording = threading.Event()
        with mic.recorder(samplerate=SAMPLERATE) as r:
            while True:
                _data = r.record(numframes=int(SAMPLERATE*INTERVAL_DURATION))
                if data is None:
                    data = _data
                else:
                    data = np.concatenate((data, _data))
                if recording.is_set():
                    recording = None
                    break
    except KeyboardInterrupt:
        pass
    finally:
        print("Saving audio file")
        sf.write(file=filepath, data=data, samplerate=SAMPLERATE)


model = load_silero_vad()


def monitorSystemAudio(widget, storage, info):
    global monitoringAudio
    PAUSE = 0
    SAMPLERATE = 44100
    INTERVAL_DURATION = 512/16000  # 0.1
    resampler = torchaudio.transforms.Resample(SAMPLERATE, 16000)
    try:
        monitoringAudio = threading.Event()
        data = np.empty((0, mic.channels))
        # temp_data = np.empty((0, mic.channels))
        with mic.recorder(samplerate=SAMPLERATE) as r:
            while True:
                if monitoringAudio.is_set():
                    monitoringAudio = None
                    break

                _data = r.record(numframes=int(SAMPLERATE*INTERVAL_DURATION))

                data_tensor = torch.t(torch.from_numpy(_data))  # .reshape((2, -1))

                if data_tensor.size(0) > 1:
                    data_tensor = data_tensor.mean(dim=0, keepdim=True)

                if SAMPLERATE != 16000:
                    data_tensor = resampler(data_tensor)

                speech_prob = model(data_tensor, 16000).item()
                print(f"prob: {speech_prob};    PAUSE: {PAUSE}")

                if PAUSE > 3:
                    PAUSE = 0
                    time = data.shape[0]/SAMPLERATE
                    if time > 0.5:
                        curr_time = datetime.now()
                        if len(storage) > 4:
                            del storage[0]
                            del info[0]
                        storage.append(data)
                        info.append(f"[{curr_time.hour}:{curr_time.minute}:{curr_time.second}] {round(time, 3)}")
                        print(info)
                        widget.clear()
                        widget.addItems(info)
                        widget.item(len(info)-1).setSelected(True)
                    data = np.empty((0, mic.channels))
                    # temp_data = np.empty((0, mic.channels))
                    # break

                # if PAUSE > 2:
                #     temp_data = np.empty((0, mic.channels))

                # temp_data = np.concatenate((temp_data, _data))

                if speech_prob < 0.5:
                    PAUSE += INTERVAL_DURATION
                    continue
                else:
                    PAUSE = 0
                    data = np.concatenate((data, _data))
                    # temp_data = np.empty((0, mic.channels))

                # if data is None:
                #     data = _data
                # else:
                #     data = np.concatenate((data, _data))
    except KeyboardInterrupt:
        pass


def startMonitoring(widget, storage, info):
    if monitoringAudio is not None:
        monitoringAudio.set()
    else:
        thread = threading.Thread(
            target=monitorSystemAudio,
            args=(widget, storage, info))
        thread.start()


def record(session, audio=False, screenshot=False, tags=""):
    global hotkeys_enabled, media_dir
    hotkeys_enabled = False
    curr_time = datetime.now()

    try:
        last_note = get_last_note()
        if media_dir is None:
            media_dir = get_media_dir()
    except Exception as e:
        print(e)
        return

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

            im.save(os.path.join(media_dir, f"VN-{session}_{curr_time}.webp"))

            update_fields["Picture"] = f'<img alt="snapshot" src="VN-{session}_{curr_time}.webp">'
        except KeyboardInterrupt:
            pass

    if audio:
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

mic = None


def get_mics():
    mikes = sc.all_microphones()
    # print("\nmikes:")
    for i in range(len(mikes)):
        loopback = isloopback(mikes[i].id)
        if loopback:
            return mikes, i
    return mikes, None


use_button = True
tag = ""
