import websockets
import threading
import asyncio
import json
from datetime import datetime, timedelta
from collections import UserDict
# import traceback

from util.screenshot import _take_screenshot


class LineStored:

    def __init__(self, text):
        self.text = text
        self.next = None


class LinesTempStorage(UserDict):

    last_active_date = None
    storage_time_limit = timedelta(minutes=0, seconds=20)
    previous_line = None

    def __setitem__(self, key, value):
        if not isinstance(key, datetime):
            raise TypeError("LinesTempStorage key must be of class datetime")
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
        try:
            if self.unsent_text:
                for message in self.unsent_text:
                    await websocket.send(message)
                self.unsent_text.clear()
            async for message in websocket:
                print(message)
                pass
        except websockets.exceptions.ConnectionClosedError:
            pass
        finally:
            self.clients.remove(websocket)

    def run(self):
        async def start_server():
            while True:
                try:
                    async with websockets.serve(self.msg_handler,
                                                "0.0.0.0",
                                                self.ws_port):
                        self.main_task = asyncio.create_task(self.send_to_texthooker())
                        await self.main_task
                except Exception as e:
                    print(e)
                    await asyncio.sleep(1)

        async def main():
            global text_received
            self._loop = asyncio.get_running_loop()
            # self._loop.set_debug(True)
            text_received = asyncio.Queue()
            self._event.set()
            self.tasks = [asyncio.create_task(self.add_listener(url)) for url in self.listen_urls]
            self.tasks.append(asyncio.create_task(start_server()))
            await asyncio.gather(*self.tasks, return_exceptions=True)

        asyncio.run(main())

    async def add_listener(self, url):
        is_Luna = False
        while True:
            try:
                ws_url = f'ws://{url}'
                if is_Luna:
                    ws_url = f'ws://{url}/api/ws/text/origin'
                async with websockets.connect(ws_url, ping_interval=None) as websocket:
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
                                text_stored[line_time] = sentence
                                ss_task = asyncio.create_task(asyncio.to_thread(_take_screenshot, line_time, wait_sec=0.2))
                                self.tasks.append(ss_task)
            except Exception:
                # traceback.print_exc()
                await asyncio.sleep(1)
