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
    CGRect,
    CGPoint,
    CGSize,
)

import threading
from time import sleep
from io import BytesIO
from PIL import Image
from math import sqrt

import logging

logger = logging.getLogger("app_logger")


runLoop = NSRunLoop.currentRunLoop()


class Window:

    def __init__(self, win, parent_app, title=None, *, found_public=False, found_private=False):
        self.parent_app = parent_app
        self.title = title or self.get_title()
        self.found_public = found_public
        self.found_private = found_private
        self.CGWindowID = win["kCGWindowNumber"]

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
        return False

    def __hash__(self):
        return hash(self.CGWindowID)

    def get_title(self):
        if self.ax_win:
            return self.get_title_AX()
        return self.get_title_CG()

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


getAppWindows = getAppCGWindows


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

    def capture_screenshot(  # noqa: C901, PLR0915
        save_path: str | None = None,
        win: Window | None = None,
        screen_region: tuple | None = None,
        img_format: str = "WebP",
        max_resolution: str = "1080p",
    ) -> str | BytesIO:

        finish = threading.Event()
        file_data = None
        container = save_path or BytesIO()
        pool = NSAutoreleasePool.alloc().init()

        def shareable_content_completion_handler(shareable_content, error):
            nonlocal container

            if error is not None:
                finish.set()
                return

            if win:
                pred_format = f"windowID == {win.CGWindowID}"
                pred = NSPredicate.predicateWithFormat_(pred_format)
                capture_target_matches = shareable_content.windows().filteredArrayUsingPredicate_(pred)
                if not capture_target_matches:
                    # TODO: log and inform the user
                    container = None
                    finish.set()
                    return

                capture_target = None
                if len(capture_target_matches) > 0:
                    capture_target = capture_target_matches[0]

                if capture_target is None:
                    container = None
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
            nonlocal file_data, container

            if image is None:
                container = None
                finish.set()
                return

            bitmap_rep = NSBitmapImageRep(CGImage=image)
            data = bitmap_rep.representationUsingType_properties_(
                NSBitmapImageFileTypePNG, None
            )

            logger.debug("image size: %s", len(data))
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
