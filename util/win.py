from pywinctl import (
    getAllAppsNames,
    getAllWindows,
    Window,
)

from io import BytesIO
from PIL import ImageGrab


class App:

    def __init__(self, name):
        self._name = name

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

def capture_screenshot(save_path: str | None = None, win: Window | None = None, screen_region: tuple | None = None, img_format: str = "WebP", max_resolution: str = "1080p"):
    container = save_path or BytesIO()
    if screen_region:
        img = ImageGrab.grab(bbox=screen_region)
    else:
        img = ImageGrab.grab(window=win.getHandle())
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
