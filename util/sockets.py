import websockets
import threading
import asyncio
import json
from datetime import datetime
from collections import deque
# import traceback

from PySide6.QtCore import Signal, QObject

from util.screenshot import _take_screenshot
from util.database import GeneralSettings, linedb
from util import audio

ws_server = None
selected_line = {"line": None, "next": None, "substring_idx": None}


class SocketsSignals(QObject):
    """
    Signals to communicate with main window.

    State: 0 - stoppede,
           1 - started but not connected,
           2 - connected
    """

    ws_state = Signal(int)
    listener_state = Signal(str, int)
    line_received = Signal(object)


socket_signals = SocketsSignals()


class LineStored:

    def __init__(self, text, time):
        self.text = text
        self.time = time or datetime.now()

    def __repr__(self) -> str:
        return f"LineStored [{self.time.strftime(format="%Y-%m-%d_%H-%M-%S")}]"


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
        if self.last_active_date is None:
            last_active_date = datetime.now()
        else:
            last_active_date = self.last_active_date

        while True:
            if last_active_date - self.deque[0].time > self.storage_time_limit:
                self.deque.popleft()
            else:
                break

    def __iter__(self):
        return self.deque.__iter__()

    def __repr__(self) -> str:
        return self.deque.__repr__()


text_received = None
text_stored = LinesTempStorage()


class WebsocketManagerThread(threading.Thread):
    def __init__(self, ws_port, listen_urls=None):
        super().__init__(daemon=True)
        self._loop = None
        self.clients = set()
        self._event = threading.Event()
        self.main_task = None
        self.tasks = None
        self.ws_port = ws_port
        self.unsent_text = []
        self.listen_urls = listen_urls

    @property
    def loop(self):
        self._event.wait()
        return self._loop

    def stop_server(self):
        for task in self.tasks:
            task.cancel()
        socket_signals.ws_state.emit(0)
        socket_signals.listener_state.emit("all", 0)

    async def send_to_texthooker(self):
        while True:
            try:
                msg = await text_received.get()
                if not self.clients:
                    self.unsent_text.append(msg)
                    return
                for client in self.clients:
                    await client.send(msg)
            except Exception:
                pass

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
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    socket_signals.ws_state.emit(0)
                    print(e)
                    await asyncio.sleep(1)

        async def main():
            global text_received
            self._loop = asyncio.get_running_loop()
            # self._loop.set_debug(True)
            text_received = asyncio.Queue()
            self._event.set()
            self.tasks = [asyncio.create_task(self.new_listener(url)) for url in self.listen_urls]
            self.tasks.append(asyncio.create_task(start_server()))
            await asyncio.gather(*self.tasks, return_exceptions=True)

        asyncio.run(main())

    async def add_listener(self, url):
        task = asyncio.create_task(self.new_listener(url))
        self.tasks.append(task)

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
                    while True:
                        msg = await websocket.recv()
                        if not msg:
                            continue
                        line_time = datetime.now()
                        text_received.put_nowait(msg)
                        try:
                            data = json.loads(msg)
                            if "sentence" in data:
                                sentence = data["sentence"]
                        except json.JSONDecodeError:
                            sentence = msg
                        finally:
                            if isinstance(sentence, str):
                                text_stored.append(LineStored(text=sentence, time=line_time))
                                # print(f"audio.AudioBuffer.inactive: {audio.AudioBuffer.inactive}, audio.record_audio_buffer: {audio.record_audio_buffer}")
                                if audio.AudioBuffer.inactive and audio.record_audio_buffer:
                                    audio.record_audio_buffer.resume_recording()
                                ss_task = asyncio.create_task(asyncio.to_thread(_take_screenshot, line_time, wait_sec=0.2))
                                self.tasks.append(ss_task)
            except asyncio.CancelledError:
                pass
            except Exception:
                # print(e)
                socket_signals.listener_state.emit(url, 1)
                is_Luna = not is_Luna
                # traceback.print_exc()
                await asyncio.sleep(1)
