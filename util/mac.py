import Quartz
import ApplicationServices
import ScriptingBridge
from AppKit import (
    NSAutoreleasePool,
    NSRunLoop,
    NSDefaultRunLoopMode,
    NSPredicate,
    NSDictionary,
    NSBitmapImageFileTypePNG,
    NSBitmapImageRep,
    NSWorkspace,
    NSRunningApplication,
    NSMutableData,
    NSData,
    NSMakeRange,
    CGRect,
    CGPoint,
    CGSize,
)

import threading
from time import sleep
from io import BytesIO
from PIL import Image
from math import sqrt

import objc

"""
Bridging to undocumented private API to get CGWindowID from AXUIElement Window

    AXError _AXUIElementGetWindow(AXUIElementRef, CGWindowID* out);

usage:
err, winID = _AXUIElementGetWindow(window, None)

Undocumented API to get AXUIElement from a Data object constructed as follows

    - pid (4 bytes)
    - 0 (4 bytes)
    - 0x636f636f (4 bytes)
    - AXUIElementID (8 bytes)

    AXUIElementRef _AXUIElementCreateWithRemoteToken(CFDataRef)

usage:
AXUIElementRef (from ApplicationServices) must be imported for this to work

axUI_el = _AXUIElementCreateWithRemoteToken(data)
"""

bundle = objc.loadBundle("ApplicationServices",
    bundle_path="/System/Library/Frameworks/ApplicationServices.framework",
    module_globals=globals(),
    scan_classes=False,
)

try:
    functions = [("_AXUIElementGetWindow", objc._C_INT+b"^{__AXUIElement=}"+objc._C_OUT+objc._C_PTR+objc._C_UINT)]  # noqa: SLF001

    objc.loadBundleFunctions(bundle, globals(), functions, skip_undefined=False)
    useWindowIdPrivateAPI = True
except objc.error as e:
    useWindowIdPrivateAPI = False
    print(f"{useWindowIdPrivateAPI = }")
    print(e)

try:
    functions2 = [("_AXUIElementCreateWithRemoteToken", b"^{__AXUIElement=}"+b"^{__CFData=}")]

    objc.loadBundleFunctions(bundle, globals(), functions2, skip_undefined=False)
    useWindowsSearchPrivateAPI = True
except objc.error as e:
    useWindowsSearchPrivateAPI = False
    print(f"{useWindowsSearchPrivateAPI = }")
    print(e)

runLoop = NSRunLoop.currentRunLoop()


class MacOSError(Exception):
    """Raised for error specific to MacOS."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class Window:

    def __init__(self, win, parent_app, title=None, *, found_public=False, found_private=False):
        self.ax_win = win if isinstance(win, ApplicationServices.AXUIElementRef) else None
        self.cg_win = win if isinstance(win, NSDictionary) else None
        self.parent_app = parent_app
        self.title = title or self.get_title()
        self.found_public = found_public
        self.found_private = found_private
        self.CGWindowID = self.cg_win["kCGWindowNumber"] if self.cg_win else self.get_CGWindowID()

    def __repr__(self):
        a_name = self.parent_app if isinstance(self.parent_app, int) else self.parent_app.localizedName()
        precision = 40
        return (
            f"MacOSWindow: {{id={self.CGWindowID}; parent={a_name};"
            f" title={self.title:.{precision}}{"..." if len(self.title) > precision else ""}}}"
        )

    def __eq__(self, other):
        if not isinstance(other, Window):
            return False
        if self.CGWindowID and other.CGWindowID:
            return self.CGWindowID == other.CGWindowID
        if self.ax_win and other.ax_win:
            return self.ax_win == other.ax_win
        return False

    def __hash__(self):
        return hash(self.CGWindowID)

    def get_title(self):
        if self.ax_win:
            return self.get_title_AX()
        return self.get_title_CG()

    def get_title_AX(self):
        err, title = ApplicationServices.AXUIElementCopyAttributeValue(self.ax_win, ApplicationServices.kAXTitleAttribute, None)
        if err:
            msg = f"Failed to get 'AXTitle' with error code: {err}"
            raise MacOSError(msg)
        return title

    def get_title_CG(self):
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListExcludeDesktopElements, # | Quartz.kCGWindowListOptionOnScreenOnly,
            Quartz.kCGNullWindowID,
        )
        updated_title = next((win["kCGWindowName"] for win in windows if win["kCGWindowNumber"] == self.CGWindowID), None)
        return updated_title

    @property
    def bounds(self):
        if self.ax_win:
            return self.get_bounds_AX()
        return self.get_bounds_CG()

    def get_bounds_CG(self):
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListExcludeDesktopElements, # | Quartz.kCGWindowListOptionOnScreenOnly,
            Quartz.kCGNullWindowID,
        )
        updated_bounds = next((win["kCGWindowBounds"] for win in windows if win["kCGWindowNumber"] == self.CGWindowID), None)
        return updated_bounds

    def get_bounds_AX(self):
        pos = ApplicationServices.AXUIElementCopyAttributeValue(self.ax_win, ApplicationServices.kAXPositionAttribute, None)[1]
        pos_value = ApplicationServices.AXValueGetValue(pos, ApplicationServices.kAXValueCGPointType, None)[1]
        size = ApplicationServices.AXUIElementCopyAttributeValue(self.ax_win, ApplicationServices.kAXSizeAttribute, None)[1]
        size_value = ApplicationServices.AXValueGetValue(size, ApplicationServices.kAXValueCGSizeType, None)[1]
        bounds = {
            "Height": size_value.height,
            "Width": size_value.width,
            "X": pos_value.x,
            "Y": pos_value.y,
        }
        return bounds

    def get_CGWindowID(self):
        if useWindowIdPrivateAPI:
            err, winID = _AXUIElementGetWindow(self.ax_win, None)
            if err:
                return None
            return winID

        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListExcludeDesktopElements, # | Quartz.kCGWindowListOptionOnScreenOnly,
            Quartz.kCGNullWindowID,
        )
        a_pid = self.parent_app if isinstance(self.parent_app, int) else self.parent_app.processIdentifier()
        title = self.title
        bounds = self.bounds
        title_matches = []
        for win in windows:
            if win["kCGWindowOwnerPID"] != a_pid:
                continue
            print(f"win: {win}")
            if win["kCGWindowName"] != title:
                continue
            title_matches.append(win["kCGWindowNumber"])
            if win["kCGWindowBounds"] != bounds:
                continue
            return win["kCGWindowNumber"]
        if len(title_matches) == 1:
            return title_matches[0]



def getAllApps():
    pool = NSAutoreleasePool.alloc().init()
    matches = []
    # The list only get updated when the loop runs, so we call it for a single cycle
    runLoop.limitDateForMode_(NSDefaultRunLoopMode)
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        if app.activationPolicy() == Quartz.NSApplicationActivationPolicyRegular:
            matches.append(app)
    del pool
    return matches


def getAppCGWindows(app):
    pool = NSAutoreleasePool.alloc().init()
    a_pid = app if isinstance(app, int) else app.processIdentifier()

    def conditions(x):
        try:
            if x["kCGWindowOwnerPID"] != a_pid:
                return False
            if x["kCGWindowLayer"] > 0:
                return False
            bounds = x["kCGWindowBounds"]
            if bounds["Y"] == 0:
                return False
            if bounds["Height"] == 0 or bounds["Width"] == 0:
                return False
            title = x["kCGWindowName"]
            return bool(title)
        except KeyError:
            return False

    windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListExcludeDesktopElements, # | Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGNullWindowID,
    )
    matches = []
    for win in windows:
        if conditions(win):
            matches.append(Window(win=win, parent_app=app, title=win["kCGWindowName"]))
    del pool
    return matches


def _has_win_subrole(axUiElement):
    """Check if axUiElement is a window by verifying its Subrole."""
    err, res = ApplicationServices.AXUIElementCopyAttributeValue(axUiElement, ApplicationServices.kAXSubroleAttribute, None)
    if err:
        return False
    return res in [ApplicationServices.kAXStandardWindowSubrole, ApplicationServices.kAXDialogSubrole]


def getAppAXWindows(app):
    a_pid = app if isinstance(app, int) else app.processIdentifier()
    ax_app = ApplicationServices.AXUIElementCreateApplication(a_pid)
    err, ax_wins = ApplicationServices.AXUIElementCopyAttributeValues(ax_app, ApplicationServices.kAXWindowsAttribute, 0, 99999, None)

    if err:
        msg = f"Failed to get 'AXWindows' for pid: {a_pid} with error code: {err}"
        # TODO: Log
        return []

    windows = []

    for ax_win in ax_wins:
        if not _has_win_subrole(ax_win):
            continue
        windows.append(Window(ax_win, app, found_public=True))

    return windows


# Based on implementation in alt-tab-macos https://github.com/lwouis/alt-tab-macos/commit/2cd8b96d389004b41ce2aad5667d0a11be36dabf
def _brute_force_window_search(a_pid: int):
    remoteToken = NSMutableData(length=20)
    remoteToken.replaceBytesInRange_withBytes_(NSMakeRange(0, 4), a_pid.to_bytes(4, byteorder="little"))
    remoteToken.replaceBytesInRange_withBytes_(NSMakeRange(4, 4), bytes(4))
    remoteToken.replaceBytesInRange_withBytes_(NSMakeRange(8, 4), (0x636f636f).to_bytes(4, byteorder="little"))
    windows = []
    for i in range(1000):
        remoteToken.replaceBytesInRange_withBytes_(NSMakeRange(12, 8), i.to_bytes(8, byteorder="little"))
        axUiElement = _AXUIElementCreateWithRemoteToken(remoteToken)
        if not _has_win_subrole(axUiElement):
            continue
        windows.append(axUiElement)
    return windows


def getAllAppWindows(app, *, brute_force=True):
    a_pid = app if isinstance(app, int) else app.processIdentifier()
    windows = getAppAXWindows(a_pid)
    if useWindowsSearchPrivateAPI and brute_force:
        b_wins = [Window(w, a_pid, found_private=True) for w in _brute_force_window_search(a_pid)]
        for win in b_wins:
            try:
                win_idx = windows.index(win)
                windows[win_idx].found_private = True
            except ValueError:  # noqa: PERF203
                windows.append(win)
    return windows


getAppWindows = getAppCGWindows


def getAXWindowBounds(ax_win):
    pos = ApplicationServices.AXUIElementCopyAttributeValue(ax_win, ApplicationServices.kAXPositionAttribute, None)[1]
    if pos is None:
        return None
    pos_value = ApplicationServices.AXValueGetValue(pos, ApplicationServices.kAXValueCGPointType, None)[1]
    size = ApplicationServices.AXUIElementCopyAttributeValue(ax_win, ApplicationServices.kAXSizeAttribute, None)[1]
    if size is None:
        return None
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
        if useWindowIdPrivateAPI:
            err, winID = _AXUIElementGetWindow(ax_win, None)

            if not err and win["kCGWindowNumber"] == winID:
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

    def capture_screenshot(save_path: str | None = None, win: Window | None = None, screen_region: tuple | None = None, img_format: str = "WebP", max_resolution: str = "1080p") -> str | BytesIO:
        finish = threading.Event()
        file_data = None
        container = save_path or BytesIO()
        pool = NSAutoreleasePool.alloc().init()

        def shareable_content_completion_handler(shareable_content, error):

            if error is not None:
                finish.set()
                return

            if win:

                if win.CGWindowID:
                    pred_format = f"windowID == {win.CGWindowID}"
                else:
                    pred_format =f"(title == '{win.title}') AND (owningApplication.processID == {win.parent_app.processIdentifier()})"


                pred = NSPredicate.predicateWithFormat_(pred_format)
                capture_target_matches = shareable_content.windows().filteredArrayUsingPredicate_(pred)
                if not capture_target_matches:
                    # TODO: log and inform the user
                    finish.set()
                    return

                capture_target = None
                if len(capture_target_matches) == 1:
                    capture_target = capture_target_matches[0]
                elif len(capture_target_matches) > 1:
                    bounds = win.bounds
                    for window_capture in capture_target_matches:
                        curr_bounds = {
                            "Height": window_capture.frame().size.height,
                            "Width": window_capture.frame().size.width,
                            "X": window_capture.frame().origin.x,
                            "Y": window_capture.frame().origin.y,
                        }
                        if curr_bounds == bounds:
                            capture_target = window_capture
                            break

                if capture_target is None:
                    finish.set()
                    return

                content_filter = SCContentFilter(desktopIndependentWindow=capture_target)
            else:
                capture_target = shareable_content.displays()[0]
                content_filter = SCContentFilter(display=capture_target, excludingWindows=[])

            configuration = SCStreamConfiguration()
            configuration.setCapturesAudio_(False)
            configuration.setPreservesAspectRatio_(True)
            configuration.setShowsCursor_(False)
            configuration.setIgnoreShadowsSingleWindow_(True)
            configuration.setIgnoreGlobalClipSingleWindow_(True)
            configuration.setIgnoreShadowsDisplay_(True)
            configuration.setIgnoreGlobalClipDisplay_(True)
            configuration.setCaptureResolution_(SCCaptureResolutionBest)

            if screen_region:
                x1, y1, x2, y2 = screen_region
                # print(f"{CGRect(CGPoint(x1, y1), CGSize(x2-x1, y2-y1)) = }")
                configuration.setSourceRect_(CGRect(CGPoint(x1, y1), CGSize(x2-x1, y2-y1)))
                width = x2-x1
                height = y2-y1
            else:
                # adjust for high DPI scaling
                width = capture_target.frame().size.width*content_filter.pointPixelScale()
                height = capture_target.frame().size.height*content_filter.pointPixelScale()

            if max_resolution in resolutions:
                resolution_limit = resolutions[max_resolution]
                if width*height > resolution_limit:
                    aspect_ratio = width/height
                    height = sqrt(resolution_limit/aspect_ratio)
                    width = aspect_ratio * height

            configuration.setWidth_(width)
            configuration.setHeight_(height)

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
                img.save(container, format=img_format)

            finish.set()

        SCShareableContent.getShareableContentWithCompletionHandler_(
            shareable_content_completion_handler
        )

        finish.wait()
        del pool
        return container

except ImportError:
    # TODO: Take screenshot using PIL
    pass
