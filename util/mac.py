import Quartz
from Foundation import NSRunLoop, NSDefaultRunLoopMode, NSPredicate
import ApplicationServices
import ScriptingBridge
from AppKit import (
    NSBitmapImageFileTypePNG,
    NSBitmapImageRep,
    NSWorkspace,
)

import threading
from time import sleep
from io import BytesIO
from PIL import Image
from math import sqrt

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

# app_info = NSBundle.mainBundle().infoDictionary()
# app_info["LSBackgroundOnly"] = "1"  # suppress python macOS dock icon pop up/bounce but windows cannot be focused


runLoop = NSRunLoop.currentRunLoop()


def getAllApps():
    matches = []
    # The list only get updated when the loop runs, so we call it for a single cycle
    runLoop.limitDateForMode_(NSDefaultRunLoopMode)
    for app in NSWorkspace.sharedWorkspace().runningApplications():
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
    sleep(0.1)
    if not isCurrentlyActive(app):
        proc.setFrontmost_(True)


def isCurrentlyActive(app):
    activeAppName = NSWorkspace.sharedWorkspace().activeApplication()["NSWorkspaceApplicationKey"]
    return app == activeAppName


def getAS_SystemEvents():
    return ScriptingBridge.SBApplication.applicationWithBundleIdentifier_("com.apple.systemevents")


def getAS_Process(se, app):
    processes = se.processes()
    pred = NSPredicate.predicateWithFormat_(f"unixId == {app.processIdentifier()}")
    return processes.filteredArrayUsingPredicate_(pred)[0]


resolutions = {
    "1080p": 1920*1080,
    "720p": 1280*720,
    "480p": 854*480,
    "360p": 640*360,
}

try:
    from ScreenCaptureKit import (
        SCContentFilter,
        SCScreenshotManager,
        SCShareableContent,
        SCStreamConfiguration,
        SCCaptureResolutionBest,
    )

    def capture_screenshot(save_path: str | None = None, win=None, format: str = "WebP", max_resolution: str = "1080p") -> str | BytesIO:
        finish = threading.Event()
        file_data = None
        container = save_path or BytesIO()

        def shareable_content_completion_handler(shareable_content, error):

            if error is not None:
                print(f"err: {error}")
                return

            if win:
                pred = NSPredicate.predicateWithFormat_(f"windowID == {win["kCGWindowNumber"]}")
                capture_target = shareable_content.windows().filteredArrayUsingPredicate_(pred)[0]
                content_filter = SCContentFilter(desktopIndependentWindow=capture_target)
            else:
                capture_target = shareable_content.displays()[0]
                content_filter = SCContentFilter(display=capture_target, excludingWindows=[])

            # adjust for high DPI
            width = capture_target.frame().size.width*content_filter.pointPixelScale()
            height = capture_target.frame().size.height*content_filter.pointPixelScale()

            if max_resolution in resolutions:
                resolution_limit = resolutions[max_resolution]
                if width*height > resolution_limit:
                    aspect_ratio = width/height
                    height = sqrt(resolution_limit/aspect_ratio)
                    width = aspect_ratio * height

            configuration = SCStreamConfiguration()
            configuration.setCapturesAudio_(False)
            configuration.setWidth_(width)
            configuration.setHeight_(height)
            configuration.setPreservesAspectRatio_(True)
            configuration.setShowsCursor_(False)
            configuration.setIgnoreShadowsSingleWindow_(True)
            configuration.setIgnoreGlobalClipSingleWindow_(True)
            configuration.setIgnoreShadowsDisplay_(True)
            configuration.setIgnoreGlobalClipDisplay_(True)
            configuration.setCaptureResolution_(SCCaptureResolutionBest)

            SCScreenshotManager.captureImageWithFilter_configuration_completionHandler_(
                content_filter, configuration, capture_image_completion_handler
            )

        def capture_image_completion_handler(image, error):
            nonlocal file_data

            bitmap_rep = NSBitmapImageRep(CGImage=image)
            data = bitmap_rep.representationUsingType_properties_(
                NSBitmapImageFileTypePNG, None
            )

            print(f"image size: {len(data)}")
            file_data = BytesIO(data)
            with Image.open(file_data) as img:
                img.save(container, format=format)

            finish.set()

        SCShareableContent.getShareableContentWithCompletionHandler_(
            shareable_content_completion_handler
        )

        finish.wait()
        return container

except ImportError:
    # TODO: Take screenshot using PIL
    pass
