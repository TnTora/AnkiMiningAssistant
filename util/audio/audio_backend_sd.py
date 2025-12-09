import sounddevice as sd
import threading
from queue import Queue
from util.database import AudioSettings
from util.custom_typings import AudioInputDevice

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import numpy as np


class SD_Device:
    __slots__ = ["name", "index", "channels"]

    def __init__(self, device_dict: dict) -> None:
        self.name: str = device_dict["name"]
        self.index: int = device_dict["index"]
        self.channels: int = device_dict["max_input_channels"]


def get_audio_inputs_sd() -> tuple[list[SD_Device], int | None]:
    sd._terminate()  # noqa: SLF001
    sd._initialize()  # noqa: SLF001
    audio_inputs: list[SD_Device] = [SD_Device(device) for device in sd.query_devices() if device["max_input_channels"] > 0]
    for i, a_input in enumerate(audio_inputs):
        if a_input.name == AudioSettings.audio_input:
            return audio_inputs, i
    return audio_inputs, None


class recordingThreadSD(threading.Thread):

    def __init__(self, audio_input: AudioInputDevice) -> None:
        super().__init__()
        self.queue = Queue()
        self.stop_record_event = threading.Event()
        self.recording_started = threading.Event()
        self.audio_input = audio_input
        self.blocksize = int(AudioSettings.samplerate*AudioSettings.interval_duration)

    def stop_recording(self) -> None:
        self.stop_record_event.set()

    def callback(self, indata: "np.ndarray", frames: int, time, status: sd.CallbackFlags) -> None:
        if self.stop_record_event.is_set():
            raise sd.CallbackAbort

        _data = indata.copy()
        self.queue.put(_data)

        if not self.recording_started.is_set():
            self.recording_started.set()

    def run(self) -> None:
        stream = sd.InputStream(
            samplerate=AudioSettings.samplerate, blocksize=self.blocksize,
            device=sd.query_devices(device=self.audio_input.name, kind="input")["index"], channels=self.audio_input.channels,
            callback=self.callback, finished_callback=None)
        with stream:
            self.stop_record_event.wait()
