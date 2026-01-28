import sys
import threading
import soundcard as sc
from queue import Queue
from util.database import AudioSettings
from util.custom_typings import AudioInputDevice


def get_audio_inputs_sc() -> tuple:
    audio_inputs: list = sc.all_microphones(include_loopback=True)
    for i, a_input in enumerate(audio_inputs):
        if a_input.name == AudioSettings.audio_input:
            return audio_inputs, i
    return audio_inputs, None


class recordingThreadSC(threading.Thread):

    def __init__(self, audio_input: AudioInputDevice) -> None:
        super().__init__()
        self.queue = Queue()
        self.stop_record_event = threading.Event()
        self.recording_started = threading.Event()
        self.audio_input = audio_input

        self.blocksize = int(AudioSettings.samplerate*AudioSettings.interval_duration)
        if sys.platform == "darwin":
            self.blocksize = None


    def stop_recording(self) -> None:
        self.stop_record_event.set()


    def run(self) -> None:
        with self.audio_input.recorder(samplerate=AudioSettings.samplerate, blocksize=self.blocksize) as r:
            _data = r.record(numframes=int(AudioSettings.samplerate*AudioSettings.interval_duration))
            self.queue.put(_data)
            self.recording_started.set()

            while True:
                if self.stop_record_event.is_set():
                    break
                _data = r.record(numframes=int(AudioSettings.samplerate*AudioSettings.interval_duration))
                self.queue.put(_data)
