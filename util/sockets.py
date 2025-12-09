import websockets
import threading
import asyncio
import json
from datetime import datetime, timedelta
from collections import deque

from PySide6.QtCore import Signal, QObject

from util.screenshot import _take_screenshot
from util.database import GeneralSettings, linedb
from util import audio

import logging

logger = logging.getLogger("app_logger")

ws_server: "WebsocketManagerThread | None" = None
selected_idxs: tuple[int, ...] = ()


class SocketsSignals(QObject):
    """
    Signals to communicate with main window.

    State: 0 - stopped,
           1 - started but not connected,
           2 - connected
    """

    ws_state = Signal(int)
    listener_state = Signal(str, int)
    line_received = Signal(object)


socket_signals = SocketsSignals()


class LineStored:
    __slots__ = ["text", "time"]

    def __init__(self, text, time):
        self.text = text
        self.time = time or datetime.now()

    def __repr__(self) -> str:
        return f"LineStored [{self.time.strftime(format="%Y-%m-%d_%H-%M-%S")}| {self.text}]"


class LinesTempStorage:

    last_active_date = None
    storage_time_limit = GeneralSettings.storage_time_limit

    def __init__(self):
        self.deque = deque()
        self.load_from_db()

    def load_from_db(self):
        for data in linedb.load_lines():
            self.deque.append(LineStored(text=data[0], time=datetime.fromtimestamp(data[1])))

    def append(self, x: LineStored):
        self.deque.append(x)
        self.trim_extra()
        socket_signals.line_received.emit(x)

    def trim_extra(self):
        last_active_date = LinesTempStorage.last_active_date or datetime.now()
        # print(f"{last_active_date = }")
        while self.deque:
            offset = audio.AudioBuffer.get_timing_adjustment(last_active_date, self.deque[0].time) or timedelta(seconds=0)
            # print(f"{self.deque[0].time = }\n{offset = }\n{last_active_date - self.deque[0].time - offset = }")
            if last_active_date - self.deque[0].time - offset > self.storage_time_limit:
                self.deque.popleft()
            else:
                break

    def __iter__(self):
        return self.deque.__iter__()

    def __repr__(self) -> str:
        return self.deque.__repr__()


text_stored = LinesTempStorage()


def manual_line_selection(idxs: tuple | list) -> dict:
    text_copy = list(text_stored.deque)
    tmp_line = LineStored(text="", time=datetime.now())
    for i in idxs:
        curr_line = text_copy[i]
        tmp_line.text += " " + curr_line.text
        tmp_line.time = min(tmp_line.time, curr_line.time)
    selected_line = {"line": tmp_line, "next": None}
    if len(text_copy) > idxs[-1]+1:
        selected_line["next"] = text_copy[idxs[-1]+1]
    return selected_line


class WebsocketManagerThread(threading.Thread):
    def __init__(self, ws_port: int, listen_urls: list[str] | None = None) -> None:
        super().__init__(daemon=True)
        self._loop = None
        self.clients = set()
        self._event = threading.Event()
        self.main_task: asyncio.Task | None = None
        self.tasks: list[asyncio.Task] = []
        self.ws_port = ws_port
        self.unsent_text = []
        self.listen_urls: list[str] = listen_urls if listen_urls is not None else []
        self.text_received = asyncio.Queue()

    @property
    def loop(self):
        self._event.wait()
        return self._loop

    def stop_server(self):
        logger.info("Stopping WebSocket Server")
        for task in self.tasks:
            task.cancel()
        if self.main_task:
            self.main_task.cancel()
        socket_signals.ws_state.emit(0)
        socket_signals.listener_state.emit("all", 0)

    async def send_to_texthooker(self):
        while True:
            try:
                msg = await self.text_received.get()
                if not self.clients:
                    self.unsent_text.append(msg)
                    return
                for client in self.clients:
                    await client.send(msg)
            except asyncio.CancelledError:  # noqa: PERF203
                break
            except Exception as e:
                # TODO: Specificy exceptions
                logger.warning(e)

    async def msg_handler(self, websocket):
        self.clients.add(websocket)
        socket_signals.ws_state.emit(2)
        try:
            if self.unsent_text:
                for message in self.unsent_text:
                    await websocket.send(message)
                self.unsent_text.clear()
            async for message in websocket:
                print(message)
        except websockets.exceptions.ConnectionClosedError:
            pass
        finally:
            self.clients.remove(websocket)
            socket_signals.ws_state.emit(1)

    def run(self):
        async def start_server():
            while True:
                try:
                    async with websockets.serve(self.msg_handler,
                                                "127.0.0.1",
                                                self.ws_port):
                        socket_signals.ws_state.emit(1)
                        self.main_task = asyncio.create_task(self.send_to_texthooker())
                        await self.main_task
                except asyncio.CancelledError:  # noqa: PERF203
                    logger.info("WebSocket Server: Cancelled")
                    break
                except Exception as e:
                    socket_signals.ws_state.emit(1)
                    logger.exception("Failed to start websocket server")
                    await asyncio.sleep(1)
                else:
                    socket_signals.ws_state.emit(0)
                    logger.info("WebSocket Server: stopped")
                    break


        async def main():
            self._loop = asyncio.get_running_loop()
            # self._loop.set_debug(True)
            # self.text_received = asyncio.Queue()
            self._event.set()
            self.tasks = [asyncio.create_task(self.new_listener(url)) for url in self.listen_urls]
            self.tasks.append(asyncio.create_task(start_server()))
            await asyncio.gather(*self.tasks, return_exceptions=True)

        asyncio.run(main())

    async def add_listener(self, url):
        task = asyncio.create_task(self.new_listener(url))
        self.tasks.append(task)

    async def listener_loop(self, websocket):
        while True:
            msg = await websocket.recv()
            if not msg:
                continue
            line_time = datetime.now()
            self.text_received.put_nowait(msg)
            try:
                data = json.loads(msg)
                if "sentence" in data:
                    sentence = data["sentence"]
            except json.JSONDecodeError:
                sentence = msg
            finally:
                if isinstance(sentence, str):
                    text_stored.append(LineStored(text=sentence, time=line_time))
                    if audio.record_audio_buffer:
                        audio.record_audio_buffer.resume_recording()
                    ss_task = asyncio.create_task(asyncio.to_thread(_take_screenshot, line_time, wait_sec=0.2))
                    self.tasks.append(ss_task)

    async def new_listener(self, url):
        is_Luna = False
        socket_signals.listener_state.emit(url, 1)
        while True:
            try:
                ws_url = f"ws://{url}"
                if is_Luna:
                    ws_url = f"ws://{url}/api/ws/text/origin"
                async with websockets.connect(ws_url, ping_interval=None) as websocket:
                    socket_signals.listener_state.emit(url, 2)
                    logger.info("Listener %s: connected", url)
                    await self.listener_loop(websocket)
            except asyncio.CancelledError:  # noqa: PERF203
                logger.info("Listener %s: Cancelled", url)
                break
            except (OSError, ConnectionRefusedError, websockets.exceptions.ConnectionClosedError) as e:
                socket_signals.listener_state.emit(url, 1)
                logger.debug("Listener %s: %s", url, e)
            except websockets.exceptions.InvalidStatus as e:
                socket_signals.listener_state.emit(url, 1)
                is_Luna = not is_Luna
                logger.debug("Listener %s: %s", url, e)
            except Exception as e:
                logger.exception("listener %s", ws_url)
            else:
                socket_signals.listener_state.emit(url, 0)
                logger.info("Listener %s: stopped", url)
                break
            finally:
                await asyncio.sleep(1)
