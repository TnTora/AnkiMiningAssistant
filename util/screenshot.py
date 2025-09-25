import threading
from time import sleep
from util.util import win, session
from util.mac import capture_screenshot

images_tmp = {}


class ImageTempStorage:

    def __init__(self):
        self.img_dict = {}


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


def _take_screenshot(curr_time, wait=None):
    try:
        curr_time_str = curr_time.strftime('%Y-%m-%d_%H_%M_%S')

        if wait is not None:
            sleep(wait)

        # path_tmp = os.path.join(temp_dir, f"{session}_{curr_time_str}.webp")
        path_tmp = f"{session}_{curr_time_str}.webp"
        capture_screenshot(path_tmp, win)
        images_tmp[curr_time] = path_tmp

    except KeyboardInterrupt:
        pass


def take_screenshot():
    screenshot_thread = threading.Thread(target=_take_screenshot, daemon=True)
    screenshot_thread.start()
    return screenshot_thread
