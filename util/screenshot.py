import threading
from time import sleep
from collections import UserDict
from datetime import datetime, timedelta
from PIL import Image
import util.util as util
from util.mac import capture_screenshot


class ImageTempStorage(UserDict):

    last_active_date = None
    storage_time_limit = timedelta(minutes=5, seconds=0)

    def __setitem__(self, key, value):
        if not isinstance(key, datetime):
            raise TypeError("ImageTempStorage key must be of class datetime")
        super().__setitem__(key, value)

        if self.last_active_date is None:
            last_active_date = datetime.now()
        else:
            last_active_date = self.last_active_date

        to_remove = []
        for key_time in self.data:
            if last_active_date - key_time > self.storage_time_limit:
                to_remove.append(key_time)
            else:
                break
        for key_time in to_remove:
            del self.data[key_time]


images_tmp = ImageTempStorage()
screenshot_manager = None

# def _take_screenshot(curr_time, wait=None):
#     try:
#         bounds = getAXWindowBounds(selected_win_AX)
#         curr_time_str = curr_time.strftime('%Y-%m-%d_%H_%M_%S')

#         if wait is not None:
#             # time.sleep(wait)
#             wait_thread = threading.Thread(target=time.sleep, args=(wait,))
#             wait_thread.start()

#         if not isCurrentlyActive(app):
#             activateWindow(app, proc, selected_win_AX)

#         if wait is not None:
#             wait_thread.join()

#         rect = (int(bounds["X"]), int(bounds["Y"]), int(bounds["X"]+bounds["Width"]), int(bounds["Y"]+bounds["Height"]))
#         im = ImageGrab.grab(bbox=rect)
#         # im = ImageGrab.grab(bbox=selected_win.rect)

#         path_tmp = os.path.join(temp_dir, f"{session}_{curr_time_str}.webp")
#         im.save(path_tmp)
#         images_tmp[curr_time] = path_tmp

#     except KeyboardInterrupt:
#         pass


def _take_screenshot(curr_time: datetime | None = None, wait_sec: int | None = None):
    try:

        if curr_time is None:
            curr_time = datetime.now()

        curr_time_str = curr_time.strftime('%Y-%m-%d_%H_%M_%S')

        if wait_sec is not None:
            sleep(wait_sec)

        # path_tmp = os.path.join(temp_dir, f"{session}_{curr_time_str}.webp")
        path_tmp = f"{util.session}_{curr_time_str}.webp"
        tmp_img = capture_screenshot(path_tmp, util.win)
        images_tmp[curr_time] = tmp_img

    except KeyboardInterrupt:
        pass


def take_screenshot():
    screenshot_thread = threading.Thread(target=_take_screenshot, daemon=True)
    screenshot_thread.start()
    return screenshot_thread


class ScreenshotManager(threading.Thread):

    def __init__(self, interval=1):
        super().__init__()
        self.stop_rec = threading.Event()
        self.interval = interval

    def stop_recording(self):
        self.stop_rec.set()

    def run(self):
        while True:
            if self.stop_rec.is_set():
                break
            take_screenshot()
            sleep(self.interval)

        for time in images_tmp:
            with Image.open(images_tmp[time]) as img:
                img.save(f"screenshots/{time.strftime('%Y-%m-%d_%H_%M_%S')}.webp")

