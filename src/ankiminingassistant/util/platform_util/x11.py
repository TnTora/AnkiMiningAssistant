from pywinctl import (
    getAllAppsNames,
    getAllWindows,
    Window,
)

from io import BytesIO
from PIL import ImageGrab, Image
from Xlib.display import Display
from Xlib import X

from math import sqrt

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from os import PathLike


class App:

    def __init__(self, name):
        self._name = name

    def __eq__(self, other):
        if not isinstance(other, App):
            return False
        return self._name == other._name

    def localizedName(self):
        return self._name

def getAppWindows(app):
    windows = []
    for win in getAllWindows():
        if win.getAppName() != app.localizedName():
            continue
        windows.append(win)
    return windows

def getAllApps():
    apps = []
    for name in getAllAppsNames():
        apps.append(App(name))
    return apps

resolutions = {
    "1080p": 1920*1080,
    "720p": 1280*720,
    "480p": 854*480,
    "360p": 640*360,
}

def capture_screenshot(save_path: "PathLike | str | None" = None, win: Window | None = None, screen_region: tuple | None = None, img_format: str = "WebP", max_resolution: str = "1080p"):
    container: PathLike | str | BytesIO = save_path or BytesIO()
    if screen_region:
        img = ImageGrab.grab(bbox=screen_region)
    elif win:
        img = capture_window(win.getHandle())
    else:
        img = ImageGrab.grab()
    # resize based on max_resolution
    if max_resolution in resolutions:
        width, height = img.size
        resolution_limit = resolutions[max_resolution]
        if width*height > resolution_limit:
            aspect_ratio = width/height
            height = sqrt(resolution_limit/aspect_ratio)
            width = aspect_ratio * height
            img.resize((width, height))
    img.save(container, format=img_format)
    return container

def capture_window(window_handle):
    display = Display()
    root = display.screen().root

    window = display.create_resource_object("window", window_handle)
    geometry = window.get_geometry()
    width, height = geometry.width, geometry.height
    pixmap = window.get_image(0, 0, width, height, X.ZPixmap, 0xffffffff)
    data = pixmap.data
    # final_image = Image.frombytes("RGB", size, data, "raw", "BGRX", size[0] * 4, 1)
    final_image = Image.frombytes("RGB", (width, height), data, "raw", "BGRX")

    display.close()
    return final_image
