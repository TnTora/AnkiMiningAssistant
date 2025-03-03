import json
import urllib.request
# import shlex
# import subprocess
import os
import sys
import numpy as np
import soundcard as sc
import soundfile as sf
# import pywinctl as pwc
from datetime import datetime
from time import sleep, time
from PIL import ImageGrab  # , Image

import AppKit
import Quartz
from Foundation import NSRunLoop, NSDefaultRunLoopMode, NSPredicate
import ApplicationServices
import ScriptingBridge

from AggregateDevice import createAggregateDevice, destroyAggregateDevice, isloopback

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


from pynput import mouse  # noqa

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
    print(f"isCurrentlyActive: {isCurrentlyActive(app)}")
    sleep(0.1)
    print(f"isCurrentlyActive: {isCurrentlyActive(app)}")
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
    SAMPLERATE = 44100
    INTERVAL_DURATION = 0.1
    data = None
    try:
        with mic.recorder(samplerate=SAMPLERATE) as r:
            while True:
                _data = r.record(numframes=int(SAMPLERATE*INTERVAL_DURATION))
                if data is None:
                    data = _data
                else:
                    data = np.concatenate((data, _data))
    except KeyboardInterrupt:
        sf.write(file=filepath, data=data, samplerate=SAMPLERATE)


def record(session, audio=False, screenshot=False, tags=""):
    curr_time = datetime.now()

    try:
        last_note = get_last_note()
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
            mouse_controller.position = (
                bounds["X"]+(button["x_rel"]*bounds["Width"]),
                bounds["Y"]+(button["y_rel"]*bounds["Height"])
            )
            sleep(0.1)
            mouse_controller.click(mouse.Button.left, 1)
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


def updateSessions():
    with open(os.path.join(directory, "sessions.json"), "w") as f:
        json.dump(sessions, f, indent=4)


def SessionConfig(new=False):
    global sessions, session_name, button, app, proc, selected_win, selected_win_AX
    while True:
        if not new:
            print(
                f"{"-"*50}\n\n"
                f"[1] Session Name: {session_name}\n"
                f"[2] Application: {app.localizedName()}\n"
                f"    Window Title: {selected_win["kCGWindowName"]}\n"
                f"[3] Audio Button: {button}\n"
                f"[b] Back\n"
                f"[q] Quit\n"
                f"\n{"-"*50}"
            )
            type_selection = str(input("Choose: ")).strip()
        else:
            type_selection = None

        if type_selection == "b":
            return main()
        if type_selection == "q":
            return

        if new or type_selection == "1":
            old_session_name = session_name
            session_name = input("Write session name: ").strip()
            sessions.pop(old_session_name)

        if new or type_selection == "2":
            apps = getAllApps()
            apps_names = [a.localizedName() for a in apps]

            for i in range(len(apps_names)):
                print(f"{i}: {apps_names[i]}")

            while True:
                try:
                    idx = int(input("Choose app: "))
                    break
                except Exception:
                    pass

            app = apps[idx]
            print(f"\napp: {app}")
            proc = getAS_Process(se, app)
            print(f"process: {proc.name()}")

            app_windows = getAppWindows(app)
            app_windows_AX = getAppAXWindows(app)

            if len(app_windows) == 1:
                selected_win = app_windows[0]
            else:
                for i in range(len(app_windows)):
                    print(f"{i}: {app_windows[i]["kCGWindowName"]}")
                while True:
                    try:
                        idx = int(input("Choose window: "))
                        break
                    except Exception:
                        pass
                selected_win = app_windows[idx]

            # print(app_windows_AX)
            selected_win_AX = getAXWindowFromWindowInfo(app_windows_AX, selected_win)

            if selected_win_AX is None:
                print("Failed to get window element")
                sys.exit()

        if new or type_selection == "3":
            input("Press ENTER then click on the button to replay sentence audio")
            activateWindow(app, proc, selected_win_AX)
            # Collect events until released
            with mouse.Listener(on_click=on_click) as listener:
                listener.join()

            button = {}
            button["x_rel"] = (targetX - selected_win["kCGWindowBounds"]["X"]) / selected_win["kCGWindowBounds"]["Width"]
            button["y_rel"] = (targetY - selected_win["kCGWindowBounds"]["Y"]) / selected_win["kCGWindowBounds"]["Height"]

        if type_selection not in ["1", "2", "3", None]:
            print("invalid choice")
            continue

        sessions[session_name] = {
            "AppName": app.localizedName(),
            "WindowTitle": selected_win["kCGWindowName"],
            "Button": button
        }
        updateSessions()


input("Make sure audio output device and terminal permission are set up correctly then press ENTER")

directory = os.path.split(os.path.realpath(__file__))[0]

if not os.path.isfile(os.path.join(directory, "sessions.json")):
    with open(os.path.join(directory, "sessions.json"), "w") as f:
        json.dump({}, f)

with open(os.path.join(directory, "sessions.json")) as f:
    try:
        sessions = json.load(f)
    except ValueError:
        sessions = {}
        # json.dump(sessions, f, indent=4)

# sessions = {
#     "SessionName": {
#         "AppName": "app.localizedName()",
#         "WindowTitle": "kCGWindowName"
#     }
# }

session = None
session_name = None
button = None

if len(sessions) > 0:
    while True:
        key_list = list(sessions.keys())

        print("-"*50)
        for i in range(len(key_list)):
            print(f"[{i}]: {key_list[i]}")
        print("-"*50)

        print(
            "To select a session type the corresponding index\n"
            "To create a new session type 'n'\n"
            "To quit type 'q'\n"
        )
        user_input = input("Input: ").strip().lower()
        print("-"*50)

        if not user_input:
            continue

        if user_input == "q":
            sys.exit()

        if user_input == "n":
            break

        try:
            idx = int(user_input)
        except ValueError:
            try:
                idx = int(user_input)
            except ValueError:
                print("Invalid input")
                continue

        if idx < 0 or idx > len(key_list)-1:
            print("\nInvalid index")
            continue

        session_name = key_list[idx]
        session = sessions[session_name]
        break

se = getAS_SystemEvents()

if session is None:
    SessionConfig(new=True)
else:
    apps = getAllApps()
    apps_names = [a.localizedName() for a in apps]

    app = [a for a in apps if a.localizedName() == session["AppName"]][0]

    app_windows = getAppWindows(app)
    app_windows_AX = getAppAXWindows(app)

    if len(app_windows) == 1:
        selected_win = app_windows[0]
    else:
        selected_win = [win for win in app_windows if win["kCGWindowName"] == session["WindowTitle"]][0]

    selected_win_AX = getAXWindowFromWindowInfo(app_windows_AX, selected_win)

    if selected_win_AX is None:
        print("Failed to get window element")
        sys.exit()

    button = session["Button"]

print(f"\nselected_win: {selected_win}\n\nselected_win_AX: {selected_win_AX}\n")
print("-"*50)


aggr_device = createAggregateDevice()

mic = None
mikes = sc.all_microphones()
print("\nmikes:")
for i in range(len(mikes)):
    loopback = isloopback(mikes[i].id)
    if loopback:
        mic = mikes[i]
    print(f"{i}: {mikes[i]}, is loopback: {loopback}")
print(f"\nSelected mic: {mic}")


use_button = True


def main():
    while True:
        global use_button
        print(
            f"{"-"*50}"
            f"\n\nSession Name: {session_name}\n"
            f"Application: {app.localizedName()}\n"
            f"Window Title: {selected_win["kCGWindowName"]}\n"
            f"Audio Button: {button}\n"
            f"Use Audio Button: {use_button}\n\n"
            f"{"-"*50}"
        )
        type_selection = str(input(
            "\n[1] Screenshot\n"
            "[2] Audio\n"
            "[3] Both\n"
            "[b] Switch button on/off\n"
            "[m] Modify Session Settings\n"
            "[q] Quit\n"
            "Choose: ")).strip()
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
        elif type_selection == "m":
            return SessionConfig()
        elif type_selection == "b":
            use_button = not use_button
        elif type_selection == "q":
            break
        else:
            print("invalid choice")


main()

if aggr_device:
    destroyAggregateDevice()
