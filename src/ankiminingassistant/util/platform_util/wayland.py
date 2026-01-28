from PySide6.QtCore import QObject, Signal

from jeepney import DBusAddress, new_method_call
from jeepney.bus_messages import MatchRule, message_bus
from jeepney.io.blocking import Proxy, open_dbus_connection

from io import BytesIO
from PIL import Image

from math import sqrt

import pipewire
import threading
import os

from util.database import settings

import logging

logger = logging.getLogger("app_logger")


def getAppWindows(app):
    return []

def getAllApps():
    return []

resolutions = {
    "1080p": 1920*1080,
    "720p": 1280*720,
    "480p": 854*480,
    "360p": 640*360,
}

# -------- dbus xdg-desktop-portal-------------

class PortalError(Exception):

    def __init__(self, message, interface, err_code):
        super().__init__(message)
        self.message = message
        self.interface = interface
        self.err_code = err_code

    def __str__(self):
        return f"{self.interface}: {self.message} (response: {self.err_code})"


class ScreenCast:

    src_type = {
        "MONITOR": 1,
        "WINDOW": 2,
    }

    def __init__(self, restore_token: str | None = None):
        self.portal = DBusAddress(
            object_path="/org/freedesktop/portal/desktop",
            bus_name="org.freedesktop.portal.Desktop",
        )
        self.screencast = self.portal.with_interface("org.freedesktop.portal.ScreenCast")
        self.session_token = "screencast_session_token"  # noqa: S105
        self.session_handle = None
        self.node_id = None
        self.restore_token = {
            "WINDOW": restore_token,
            "MONITOR": None,
        }
        self.conn = open_dbus_connection()
        self.sender_name = self.conn.unique_name[1:].replace(".", "_")
        self.session_open = False

    def close_session(self):
        session_object = DBusAddress(
            object_path=self.session_handle,
            bus_name="org.freedesktop.portal.Desktop",
        )
        session = session_object.with_interface("org.freedesktop.portal.Session")
        req = new_method_call(
                session,
                "Close",
            )
        self.conn.send(req)
        self.session_open = False

    def close_conn(self):
        if self.session_open:
            self.close_session()
        self.conn.close()

    def new_session(self, src_type: str = "WINDOW"):

        self.create_session()

        self.select_sources(src_type)

        self.start_session(src_type)

        self.session_open = True
        return self.node_id, self.restore_token

    def get_handle(self, token):
        return f"/org/freedesktop/portal/desktop/request/{self.sender_name}/{token}"

    def call_method(self, token: str, method_name: str, signature: str, options: tuple):

        response_rule = MatchRule(
            type="signal", interface="org.freedesktop.portal.Request", path=self.get_handle(token)
        )
        Proxy(message_bus, self.conn).AddMatch(response_rule)

        with self.conn.filter(response_rule) as responses:
            req = new_method_call(
                self.screencast,
                method_name,
                signature,
                options,
            )
            self.conn.send_and_get_reply(req)
            response_msg = self.conn.recv_until_filtered(responses)

        response, results = response_msg.body

        if response == 0:
            logger.debug("%s results: %s", method_name, results)
            return results

        msg = f"method '{method_name}' failed."
        raise PortalError(msg, interface="org.freedesktop.portal.ScreenCast", err_code=response)

    def create_session(self):
        options = {
            "handle_token": ("s", "create_session"),
            "session_handle_token": ("s", self.session_token),
        }
        repl = self.call_method(token="create_session", method_name="CreateSession", signature="a{sv}", options=(options,))  # noqa: S106

        self.session_handle = repl["session_handle"][1]
        logger.debug("session handle: %s", self.session_handle)

    def select_sources(self, src_type: str = "WINDOW"):
        options = {
            "handle_token": ("s", "select_sources"),
            "types": ("u", self.src_type[src_type]),
            "persist_mode": ("u", 2),
        }
        if self.restore_token[src_type] is not None:
            options["restore_token"] = ("s", self.restore_token[src_type])
        repl = self.call_method(token="select_sources", method_name="SelectSources", signature="oa{sv}", options=(self.session_handle, options))  # noqa: S106
        logger.info("Source Selected")

    def start_session(self, src_type: str = "WINDOW"):
        options = {
            "handle_token": ("s", "start"),
        }
        repl = self.call_method(token="start", method_name="Start", signature="osa{sv}", options=(self.session_handle, "", options))  # noqa: S106

        self.node_id = repl["streams"][1][0][0]

        if "restore_token" in repl:
            self.restore_token[src_type] = repl["restore_token"][1]

        logger.debug("node id: %s", self.node_id)


class ScreenShot:

    src_type = {
        "MONITOR": 1,
        "WINDOW": 2,
    }

    def __init__(self):
        self.portal = DBusAddress(
            object_path="/org/freedesktop/portal/desktop",
            bus_name="org.freedesktop.portal.Desktop",
        )
        self.screenshot = self.portal.with_interface("org.freedesktop.portal.Screenshot")
        self.handle_token = "screenshot_handle_token"  # noqa: S105

    def grab(self):
        conn = open_dbus_connection()
        sender_name = conn.unique_name[1:].replace(".", "_")
        logger.debug("sender name: %s", sender_name)

        handle = f"/org/freedesktop/portal/desktop/request/{sender_name}/{self.handle_token}"

        response_rule = MatchRule(
            type="signal", interface="org.freedesktop.portal.Request", path=handle
        )
        Proxy(message_bus, conn).AddMatch(response_rule)

        options = {
            "handle_token": ("s", self.handle_token),
            "modal": ("b", True),
            "interactive": ("b", False)
        }

        with conn.filter(response_rule) as responses:
            req = new_method_call(
                self.screenshot,
                "Screenshot",
                "sa{sv}",
                ("", options),
            )
            conn.send_and_get_reply(req)
            response_msg = conn.recv_until_filtered(responses)

        response, results = response_msg.body
        conn.close()

        if response != 0:
            # raise exception for failure
            # TODO: create custom error and/or decide wheter to retry or close the connection
            msg = f"Screenshot failed."
            raise PortalError(msg, interface="org.freedesktop.portal.Screenshot", err_code=response)
        logger.debug("ScreenShot grab results: %s", results)
        filepath = results["uri"][1].split("file://", 1)[-1]
        img = Image.open(filepath)
        # remove original file
        os.remove(filepath)  # noqa: PTH107
        return img

# -------- retrieve obj serial from node id --------------


def make_registry_handle(fct_name, extra_data):

    def cb(obj_id, permissions, obj_type, version, props):
        if extra_data["node_id"] and obj_id != extra_data["node_id"]:
            pipewire.lib.pw_main_loop_quit(extra_data["loop"])
            return

        logger.debug("object: id:%s type:%s/%s", obj_id, pipewire.ffi.string(obj_type).decode(), version)

        for i in range(props.n_items):
            if pipewire.ffi.string(props.items[i].key) != b"object.serial":
                continue
            extra_data["result"] = pipewire.ffi.string(props.items[i].value)
            logger.debug("%s: %s", pipewire.ffi.string(props.items[i].key), pipewire.ffi.string(props.items[i].value))
            break

        pipewire.lib.pw_main_loop_quit(extra_data["loop"])

    return pipewire.ffi.new_handle({fct_name: cb})


def get_obj_serial(node_id=None):
    registry_listener = pipewire.ffi.new("struct spa_hook *")
    registry_events = pipewire.ffi.new("struct pw_registry_events *")
    registry_events.version = pipewire.lib.PW_VERSION_REGISTRY_EVENTS
    setattr(registry_events, "global", pipewire.lib.py_cb_pw_registry_event_global)

    pipewire.lib.pw_init(pipewire.ffi.NULL, pipewire.ffi.NULL)

    loop = pipewire.lib.pw_main_loop_new(pipewire.ffi.NULL)
    context = pipewire.lib.pw_context_new(pipewire.lib.pw_main_loop_get_loop(loop), pipewire.ffi.NULL, 0)

    core = pipewire.lib.pw_context_connect(context, pipewire.ffi.NULL, 0)

    registry = pipewire.lib.pw_core_get_registry(core, pipewire.lib.PW_VERSION_REGISTRY, 0)

    cb_data = {
        "loop": loop,
        "node_id": node_id,
        "result": None,
    }
    cb_handle = make_registry_handle("global", cb_data)

    pipewire.lib.pw_registry_add_listener(registry, registry_listener, registry_events, cb_handle)

    pipewire.lib.pw_main_loop_run(loop)

    pipewire.lib.pw_proxy_destroy(pipewire.ffi.cast("struct pw_proxy *", registry))
    pipewire.lib.pw_core_disconnect(core)
    pipewire.lib.pw_context_destroy(context)
    pipewire.lib.pw_main_loop_destroy(loop)

    return cb_data["result"]


# -------------- access pipewire stream to get frames -------------------


class PipewireStream(threading.Thread):

    def __init__(self, node_serial):
        super().__init__()
        self.width, self.height = 0, 0
        self.loop = None
        self.node_serial = node_serial
        self.curr_frame = None

    def stop_loop(self):
        pipewire.lib.pw_main_loop_quit(self.loop)

    def make_stream_handle(self, extra_data):
        def cb_process():
            b = pipewire.lib.pw_stream_dequeue_buffer(extra_data["stream"])
            if b == pipewire.ffi.NULL:
                logger.debug("Pipewire: out of buffers")
                return

            buf = b.buffer
            if buf.datas[0].data == pipewire.ffi.NULL:
                return

            # print(f"got a frame of size {buf.datas[0].chunk.size}")

            self.curr_frame = buf.datas[0]

            pipewire.lib.pw_stream_queue_buffer(extra_data["stream"], b)

        def cb_param_changed(obj_id, param):
            if param == pipewire.ffi.NULL or obj_id != pipewire.lib.SPA_PARAM_Format:
                return

            if pipewire.lib.spa_format_parse(param, pipewire.ffi.addressof(extra_data["format"], "media_type"), pipewire.ffi.addressof(extra_data["format"], "media_subtype")) < 0:
                return

            if extra_data["format"].media_type != pipewire.lib.SPA_MEDIA_TYPE_video or extra_data["format"].media_subtype != pipewire.lib.SPA_MEDIA_SUBTYPE_raw:
                return

            if pipewire.lib.spa_format_video_raw_parse(param, pipewire.ffi.addressof(extra_data["format"].info, "raw")) < 0:
                return

            self.width = extra_data["format"].info.raw.size.width
            self.height = extra_data["format"].info.raw.size.height
            logger.debug("got video format:")
            logger.debug("  format: %s (%s)", extra_data["format"].info.raw.format, pipewire.ffi.string(pipewire.lib.spa_debug_type_find_name(pipewire.lib.spa_type_video_format, extra_data["format"].info.raw.format)).decode())
            logger.debug("  size: %sx%s", self.width, self.height)
            logger.debug("  framerate: %s/%s", extra_data["format"].info.raw.framerate.num, extra_data["format"].info.raw.framerate.denom)

        return pipewire.ffi.new_handle({"process": cb_process, "param_changed": cb_param_changed})


    def run(self):
        stream_events = pipewire.ffi.new("struct pw_stream_events *")
        stream_events.version = pipewire.lib.PW_VERSION_STREAM_EVENTS
        stream_events.process = pipewire.lib.py_cb_pw_stream_event_process
        stream_events.param_changed = pipewire.lib.py_cb_pw_stream_event_param_changed

        params = pipewire.ffi.new("struct spa_pod *[1]")

        buffer = pipewire.ffi.new("uint8_t[1024]")
        b = pipewire.ffi.new("struct spa_pod_builder *")
        b.data = buffer
        b.size = pipewire.ffi.sizeof(buffer)

        f = pipewire.ffi.new("struct spa_pod_frame *")

        r_def = pipewire.ffi.new("struct spa_rectangle *")
        r_def.width = 320
        r_def.height = 240
        r_min = pipewire.ffi.new("struct spa_rectangle *")
        r_min.width = 1
        r_min.height = 1
        r_max = pipewire.ffi.new("struct spa_rectangle *")
        r_max.width = 4096
        r_max.height = 4096

        f_def = pipewire.ffi.new("struct spa_fraction *")
        f_def.num = 25
        f_def.denom = 1
        f_min = pipewire.ffi.new("struct spa_fraction *")
        f_min.num = 0
        f_min.denom = 1
        f_max = pipewire.ffi.new("struct spa_fraction *")
        f_max.num = 1000
        f_max.denom = 1

        fmt = pipewire.ffi.new("struct spa_video_info *")

        pipewire.lib.pw_init(pipewire.ffi.NULL, pipewire.ffi.NULL)

        loop = pipewire.lib.pw_main_loop_new(pipewire.ffi.NULL)

        self.loop = loop

        cb_data = {"loop": loop, "format": fmt}
        cb_handle = self.make_stream_handle(cb_data)

        logger.info("Pipewire: creating stream")
        stream = pipewire.lib.pw_stream_new_simple(
            pipewire.lib.pw_main_loop_get_loop(loop),
            b"video-capture",
            pipewire.lib.pw_properties_new(
                pipewire.lib.PW_KEY_MEDIA_TYPE, pipewire.ffi.from_buffer(b"Video"),
                pipewire.lib.PW_KEY_MEDIA_CATEGORY, pipewire.ffi.from_buffer(b"Capture"),
                pipewire.lib.PW_KEY_MEDIA_ROLE, pipewire.ffi.from_buffer(b"Screen"),
                pipewire.lib.PW_KEY_TARGET_OBJECT, pipewire.ffi.from_buffer(self.node_serial),
                pipewire.ffi.NULL,
            ),
            stream_events,
            cb_handle,
        )
        cb_data["stream"] = stream

        # spa_pod_builder_add_object not available.
        # SPA_POD_Id, SPA_POD_CHOICE_ENUM_Id, SPA_POD_CHOICE_RANGE_Rectangle, SPA_POD_CHOICE_RANGE_Fraction not available.
        # SPA_RECTANGLE, SPA_FRACTION not available.
        pipewire.lib.spa_pod_builder_push_object(
            b,
            f,
            pipewire.lib.SPA_TYPE_OBJECT_Format,
            pipewire.lib.SPA_PARAM_EnumFormat,
        )
        pipewire.lib.spa_pod_builder_add(
            b,
            pipewire.ffi.cast("int", pipewire.lib.SPA_FORMAT_mediaType), pipewire.ffi.from_buffer(b"I"), pipewire.ffi.cast("int", pipewire.lib.SPA_MEDIA_TYPE_video),
            pipewire.ffi.cast("int", pipewire.lib.SPA_FORMAT_mediaSubtype), pipewire.ffi.from_buffer(b"I"), pipewire.ffi.cast("int", pipewire.lib.SPA_MEDIA_SUBTYPE_raw),
            pipewire.ffi.cast("int", pipewire.lib.SPA_FORMAT_VIDEO_format), pipewire.ffi.from_buffer(b"?eI"), pipewire.ffi.cast("int", 7),
            pipewire.ffi.cast("int", pipewire.lib.SPA_VIDEO_FORMAT_RGB),
            pipewire.ffi.cast("int", pipewire.lib.SPA_VIDEO_FORMAT_RGB),
            pipewire.ffi.cast("int", pipewire.lib.SPA_VIDEO_FORMAT_RGBA),
            pipewire.ffi.cast("int", pipewire.lib.SPA_VIDEO_FORMAT_RGBx),
            pipewire.ffi.cast("int", pipewire.lib.SPA_VIDEO_FORMAT_BGRx),
            pipewire.ffi.cast("int", pipewire.lib.SPA_VIDEO_FORMAT_YUY2),
            pipewire.ffi.cast("int", pipewire.lib.SPA_VIDEO_FORMAT_I420),
            pipewire.ffi.cast("int", pipewire.lib.SPA_FORMAT_VIDEO_size), pipewire.ffi.from_buffer(b"?rR"), pipewire.ffi.cast("int", 3),
            r_def, r_min, r_max,
            pipewire.ffi.cast("int", pipewire.lib.SPA_FORMAT_VIDEO_framerate), pipewire.ffi.from_buffer(b"?rF"), pipewire.ffi.cast("int", 3),
            f_def, f_min, f_max,
            pipewire.ffi.NULL,
        )
        params[0] = pipewire.lib.spa_pod_builder_pop(b, f)
        logger.info("Pipewire: connecting stream...")
        pipewire.lib.pw_stream_connect(
            stream,
            pipewire.lib.PW_DIRECTION_INPUT,
            pipewire.lib.PW_ID_ANY,
            pipewire.lib.PW_STREAM_FLAG_AUTOCONNECT | pipewire.lib.PW_STREAM_FLAG_MAP_BUFFERS,
            params,
            1,
        )

        pipewire.lib.pw_main_loop_run(loop)

        pipewire.lib.pw_stream_destroy(stream)
        pipewire.lib.pw_main_loop_destroy(loop)


# --------- function called from util.screenshot --------------

screencast = ScreenCast(restore_token=None)
screenshot = ScreenShot()
pipewire_stream = None

def capture_screenshot(save_path: os.PathLike | str | None = None, win = None, screen_region: tuple | None = None, img_format: str = "WebP", max_resolution: str = "1080p"):
    container = save_path or BytesIO()

    if pipewire_stream is None: # settings.general.last_session == "Manual":
        img = screenshot.grab()
    elif not(pipewire_stream is None or pipewire_stream.curr_frame is None):
        # construct Image from the data obtained using pipewire
        # TODO: get format from pipewire
        img = Image.frombytes(
            "RGB",
            (pipewire_stream.width, pipewire_stream.height),
            bytes(pipewire.ffi.buffer(pipewire_stream.curr_frame.data, pipewire_stream.curr_frame.chunk.size)),
            "raw",
            "BGRX"
        )
    else:
        return None

    if screen_region:  # noqa: SIM108
        img = img.crop(screen_region)
    else:
        # crop blackspace
        img = img.crop(img.getbbox())

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

def set_sources():
    if screencast.session_open:
        # TODO: inform user
        return
    screencast.restore_token["WINDOW"] = None
    screencast.new_session()
    screencast.close_session()

def start_screencapture(src_type: str = "WINDOW"):
    global pipewire_stream  # noqa: PLW0603
    screencast.new_session(src_type)
    obj_serial = get_obj_serial(screencast.node_id)
    pipewire_stream = PipewireStream(obj_serial)
    pipewire_stream.start()
    logger.info("Screencapture started")

def stop_screencapture():
    global pipewire_stream  # noqa: PLW0603
    screencast.close_session()
    pipewire_stream.stop_loop()
    pipewire_stream.join()
    pipewire_stream = None
    logger.info("Screencapture stopped")
