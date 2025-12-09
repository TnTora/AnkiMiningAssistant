import ctypes
import win32gui
import win32process
import win32con
from win32com.client import GetObject

from io import BytesIO
from PIL import ImageGrab
from math import sqrt

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from os import PathLike


class App:

    def __init__(self, name, pid):
        self._name = name
        self._pid = pid

    def __eq__(self, other):
        if not isinstance(other, App):
            return False
        return self._pid == other._pid

    def __hash__(self):
        return hash(self._pid)

    def localizedName(self):
        return self._name

    def processIdentifier(self):
        return self._pid


class Window:

    def __init__(self, hwnd, parent_app):
        self.parent_app = parent_app
        self.hwnd = hwnd

    def __repr__(self):
        a_name = self.parent_app.localizedName()
        precision = 40
        return (
            f"Window: hwnd={self.hwnd}; parent={a_name};"
            f" title={self.title:.{precision}}{"..." if len(self.title) > precision else ""};"
        )

    def __eq__(self, other):
        if not isinstance(other, Window):
            return False
        return self.hwnd == other.hwnd

    def __hash__(self):
        return hash(self.hwnd)

    @property
    def title(self) -> str:
        name = win32gui.GetWindowText(self.hwnd)
        if isinstance(name, bytes):
            name = name.decode()
        return name or ""


def getAppWindows(app):
    windows = []

    def winEnumHandler(hwnd: int, ctx) -> bool:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        title = win32gui.GetWindowText(hwnd)

        if not title:
            return True

        if win32gui.IsWindowVisible(hwnd) and pid == app.processIdentifier():
            windows.append(Window(hwnd, app))
        return True

    win32gui.EnumWindows(winEnumHandler, None)
    return windows

def _getFilteredAppsPid():
    apps_pid = set()

    def winEnumHandler(hwnd: int, ctx):
        if not win32gui.IsWindowVisible(hwnd):
            return True

        # DWM Cloaked Check: https://stackoverflow.com/questions/64586371/filtering-background-processes-pywin32
        isCloaked = ctypes.c_int(0)
        DWMWA_CLOAKED = 14
        ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(isCloaked), ctypes.sizeof(isCloaked))

        # if win32gui.IsWindowVisible(hwnd) and isCloaked.value == 0:
        if isCloaked.value == 0:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            apps_pid.add(pid)
        return True

    win32gui.EnumWindows(winEnumHandler, None)
    return apps_pid

# https://stackoverflow.com/questions/550653/cross-platform-way-to-get-pids-by-process-name-in-python
def getAllApps():
    WMI = GetObject("winmgmts:")
    processes = WMI.InstancesOf("Win32_Process")
    filtered_pids = _getFilteredAppsPid()
    apps = []
    for p in processes:
        p_name = p.Properties_("Name").Value
        pid = p.Properties_("ProcessID").Value
        if pid in filtered_pids:
            apps.append(App(p_name, pid))
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
        img = ImageGrab.grab(window=win.hwnd)
    else:
        # take screenshot of the full screen
        img = ImageGrab.grab()

    # resize based on max_resolution
    if max_resolution in resolutions:
        width, height = img.size
        resolution_limit = resolutions[max_resolution]
        if width*height > resolution_limit:
            aspect_ratio = width/height
            height = int(sqrt(resolution_limit/aspect_ratio))
            width = int(aspect_ratio * height)
            img.resize((width, height))
    img.save(container, format=img_format)
    return container
