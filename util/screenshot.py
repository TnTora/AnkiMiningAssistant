import threading
from time import sleep
from collections import deque
from datetime import datetime, timedelta
from io import BytesIO

# from PIL import Image
from util.audio import AudioBuffer
from util.platform_util import capture_screenshot
from util.database import GeneralSettings, ImageSettings, imagedb, sessionsdb
# import util.util as util

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from os import PathLike
    from util.platform_util import Window

win: "Window | None" = None


class ImageStored:
    __slots__ = ["img_bytesIO", "time"]

    def __init__(self, img_bytesIO, time=None) -> None:
        self.img_bytesIO = img_bytesIO
        self.time = time or datetime.now()

    def __repr__(self) -> str:
        return f"ImageStored [{self.time.strftime(format="%Y-%m-%d_%H-%M-%S")}]"

    def size(self):
        return self.img_bytesIO.getbuffer().nbytes


class ImageTempStorage:

    # TODO: at startup last_active_date should be equal to start_time of last inactive_interval if present
    last_active_date = None
    storage_time_limit = GeneralSettings.storage_time_limit
    inactive = True

    def __init__(self):
        self.deque = deque()
        self.load_from_db()

    def load_from_db(self):
        for data, timestamp in imagedb.load_imgs():
            self.deque.append(ImageStored(img_bytesIO=BytesIO(data), time=datetime.fromtimestamp(timestamp)))

    def append(self, x):
        self.deque.append(x)
        self.trim_extra()

    def trim_extra(self):
        last_active_date = ImageTempStorage.last_active_date or datetime.now()

        while self.deque:
            offset = AudioBuffer.get_timing_adjustment(last_active_date, self.deque[0].time) or timedelta(seconds=0)
            if last_active_date - self.deque[0].time - offset > ImageTempStorage.storage_time_limit:
                self.deque.popleft()
            else:
                break

    def __iter__(self):
        return self.deque.__iter__()

    def __getitem__(self, index):
        return self.deque[index]

    def __len__(self):
        return self.deque.__len__()

    def __repr__(self) -> str:
        return self.deque.__repr__()


images_tmp = ImageTempStorage()
screenshot_manager: "ScreenshotManager | None" = None


def _take_screenshot(curr_time: datetime | None = None, wait_sec: float | None = None, save_path: "PathLike | str | None" = None) -> None:
    try:

        if wait_sec is not None:
            sleep(wait_sec)

        screen_region = sessionsdb.current_session["screen_region"] if sessionsdb.current_session["use_screen_region"] else None

        if screen_region and ImageSettings.pixel_ratio:
            offsets = (
                ImageSettings.offsets["x"],
                ImageSettings.offsets["y"],
                ImageSettings.offsets["x"],
                ImageSettings.offsets["y"],
            )
            screen_region = tuple(int(ImageSettings.pixel_ratio*(a+b)) for a, b in zip(screen_region, offsets, strict=True))

        tmp_img: PathLike | str | BytesIO = capture_screenshot(save_path, win, screen_region=screen_region, img_format=ImageSettings.format)

        if isinstance(tmp_img, BytesIO):
            images_tmp.append(ImageStored(img_bytesIO=tmp_img, time=curr_time))

    except KeyboardInterrupt:
        # TODO: Change errors to handle or ignore
        pass


def take_screenshot() -> threading.Thread:
    screenshot_thread = threading.Thread(target=_take_screenshot, daemon=True)
    screenshot_thread.start()
    return screenshot_thread


class ScreenshotManager(threading.Thread):

    def __init__(self, interval=1) -> None:
        super().__init__()
        self.stop_rec = threading.Event()
        self.interval = interval

    def stop_recording(self) -> None:
        self.stop_rec.set()

    def run(self) -> None:
        while True:
            if self.stop_rec.is_set():
                break
            if ImageTempStorage.inactive:
                sleep(self.interval)
                continue
            take_screenshot()
            sleep(self.interval)
