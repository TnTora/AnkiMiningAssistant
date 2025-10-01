import threading
from time import sleep
from collections import deque
from datetime import datetime

# from PIL import Image
from util.mac import capture_screenshot
from util.database import GeneralSettings, ImageSettings, imagedb
# import util.util as util

win = None


class ImageStored:

    def __init__(self, img_bytesIO, time=None):
        self.img_bytesIO = img_bytesIO
        self.time = time or datetime.now()

    def __repr__(self) -> str:
        return f"ImageStored [{self.time.strftime(format="%Y-%m-%d_%H-%M-%S")}]"

    def size(self):
        return self.img_bytesIO.getbuffer().nbytes


class ImageTempStorage:

    last_active_date = None
    storage_time_limit = GeneralSettings.storage_time_limit
    inactive = True

    def __init__(self):
        self.deque = deque()
        self.load_from_db()

    def load_from_db(self):
        for data in imagedb.load_imgs():
            self.deque.append(ImageStored(img_bytesIO=data[0], time=datetime.fromtimestamp(data[1])))

    def append(self, x):
        self.deque.append(x)
        self.trim_extra()

    def trim_extra(self):
        if ImageTempStorage.last_active_date is None:
            last_active_date = datetime.now()
        else:
            last_active_date = ImageTempStorage.last_active_date

        while self.deque:
            if last_active_date - self.deque[0].time > ImageTempStorage.storage_time_limit:
                self.deque.popleft()
            else:
                break

    def __iter__(self):
        return self.deque.__iter__()

    def __repr__(self) -> str:
        return self.deque.__repr__()


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


def _take_screenshot(curr_time: datetime | None = None, wait_sec: int | None = None, save_on_disk: bool = False):
    try:

        if curr_time is None:
            curr_time = datetime.now()

        curr_time_str = curr_time.strftime('%Y-%m-%d_%H_%M_%S')

        if wait_sec is not None:
            sleep(wait_sec)

        # path_tmp = os.path.join(temp_dir, f"{session}_{curr_time_str}.webp")
        path_tmp = f"{curr_time_str}.webp" if save_on_disk else None
        tmp_img = capture_screenshot(path_tmp, win, format=ImageSettings.format)
        # images_tmp[curr_time] = tmp_img
        images_tmp.append(ImageStored(img_bytesIO=tmp_img, time=curr_time))

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
            if ImageTempStorage.inactive:
                sleep(self.interval)
                continue
            take_screenshot()
            sleep(self.interval)

        # for img in images_tmp:
        #     with open(f"screenshots/{img.time.strftime('%Y-%m-%d_%H_%M_%S')}.webp", "wb") as f:
        #         f.write(img.img_bytesIO.getbuffer())

