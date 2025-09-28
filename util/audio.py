import threading
import torch
import torchaudio
import numpy as np
import soundcard as sc
import soundfile as sf
from silero_vad import load_silero_vad
from time import sleep
from datetime import datetime, timedelta
from util.AggregateDevice import isloopback
from collections import deque
from itertools import islice

import util.screenshot as screenshot

monitoringAudio = None
SAMPLERATE = 44100
INTERVAL_DURATION = 512/16000  # 0.1
mic = None
buffer = None
secondary_buffer = None
record_audio_buffer = None
PLAYBACK = False

model = load_silero_vad()
resampler = torchaudio.transforms.Resample(SAMPLERATE, 16000)


class AudioInterval:

    def __init__(self, audio, vad=None) -> None:
        self.audio = audio
        self.vad = vad


class InactiveInterval:

    def __init__(self, start_time):
        self.start_time = start_time
        self.end_time = None


class AudioBuffer:

    storage_time_limit = timedelta(minutes=5, seconds=0)
    inactive_intervals = []
    inactive = False

    def __init__(self, channels=2, max_time=None):
        max_time = max_time or AudioBuffer.storage_time_limit.total_seconds()
        max_intervals = int(max_time // INTERVAL_DURATION)+1
        self.deque = deque(maxlen=max_intervals)
        self.channels = channels

    def update(self, new_audio, new_vad):
        self.deque.append(AudioInterval(audio=new_audio, vad=new_vad))

    def __iter__(self):
        return self.deque.__iter__()

    def __len__(self):
        return self.deque.__len__()

    @property
    def data(self, start_idx=0, end_idx=None):
        end_idx = end_idx or len(self.deque)

        data = np.concatenate(
            [interval.audio for interval in self.slice_(start_idx, end_idx)],
            axis=0,
        )

        return data

    def slice_(self, start_idx=None, end_idx=None):
        return islice(self.deque, start_idx, end_idx)

    @classmethod
    def get_total_offset(cls):
        offset = timedelta(seconds=0)

        for interval in cls.inactive_intervals:
            if interval.end_time is None:
                continue
            offset += interval.end_time - interval.start_time

        return offset

    @classmethod
    def pause(cls):
        cls.inactive = True
        screenshot.ImageTempStorage.inactive = True
        offset = timedelta(seconds=0)
        remove_up_to = 0
        curr_time = datetime.now()

        for interval in reversed(cls.inactive_intervals):

            if curr_time - interval.end_time - offset > cls.storage_time_limit:
                remove_up_to = cls.inactive_intervals.index(interval) + 1
                break

            offset += interval.end_time - interval.start_time

        del cls.inactive_intervals[:remove_up_to]

        cls.inactive_intervals.append(InactiveInterval(start_time=datetime.now()))

    @classmethod
    def resume(cls, offset=0):
        offset = timedelta(seconds=offset)
        cls.inactive = False
        screenshot.ImageTempStorage.inactive = False
        cls.inactive_intervals[-1].end_time = datetime.now() - offset

    @classmethod
    def get_timing_adjustment(cls, curr_time, line_time):
        offset = timedelta(seconds=0)

        for interval in reversed(cls.inactive_intervals):

            if interval.end_time is None:
                continue

            if line_time > interval.end_time:
                break

            offset += interval.end_time - interval.start_time

        return offset

    def extract_line_audio(
        self,
        line_time,
        next_line_time=None,
        save_on_disk=False,
        save_path=None,
    ):
        line_start = None
        line_end = None

        if AudioBuffer.inactive:
            curr_time = AudioBuffer.inactive_intervals[-1].start_time
        else:
            curr_time = datetime.now()

        if curr_time - line_time - AudioBuffer.get_total_offset() > AudioBuffer.storage_time_limit:
            return

        data_copy = list(self.slice_())

        if next_line_time:
            line_audio_length = next_line_time - line_time
            # print(f"line_audio_length: {line_audio_length}, in seconds: {line_audio_length.total_seconds()}")
        else:
            line_end = len(self.deque)

        timing_adjustment = AudioBuffer.get_timing_adjustment(curr_time, line_time)

        line_start = len(data_copy) - int(((curr_time - line_time) - timing_adjustment).total_seconds() // INTERVAL_DURATION)

        if line_end is None:
            line_end = line_start + int(line_audio_length.total_seconds() // INTERVAL_DURATION)

        if save_on_disk:
            save_path = save_path or f"audio_tmp/{curr_time.strftime('%Y-%m-%d_%H_%M_%S')}.mp3"
            with sf.SoundFile(file=save_path, mode="w", channels=self.channels, samplerate=SAMPLERATE) as f:
                for interval in islice(data_copy, line_start, line_end):
                    f.write(interval.audio)
            return save_path
        else:
            data_copy = np.concatenate(
                [interval.audio for interval in islice(data_copy, line_start, line_end)],
                axis=0,
            )

            return data_copy


def get_mics():
    mikes = sc.all_microphones()
    # print("\nmikes:")
    for i in range(len(mikes)):
        loopback = isloopback(mikes[i].id)
        if loopback:
            return mikes, i
    return mikes, None


def recordAudio(filepath):
    global recording
    INTERVAL_DURATION = 0.1
    data = None
    try:
        recording = threading.Event()
        with mic.recorder(samplerate=SAMPLERATE) as r:
            while True:
                _data = r.record(numframes=int(SAMPLERATE*INTERVAL_DURATION))
                if data is None:
                    data = _data
                else:
                    data = np.concatenate((data, _data))
                if recording.is_set():
                    recording = None
                    break
    except KeyboardInterrupt:
        pass
    finally:
        print("Saving audio file")
        sf.write(file=filepath, data=data, samplerate=SAMPLERATE)


class recordAudioBuffer(threading.Thread):

    resume_on_detected_voice = False

    def __init__(self):
        super().__init__()
        self.stop_rec = threading.Event()
        self.resume_rec = threading.Event()

    def stop_recording(self):
        self.stop_rec.set()

    def resume_recording(self):
        self.resume_rec.set()

    def run(self):
        try:
            PAUSE = 0
            with mic.recorder(samplerate=SAMPLERATE) as r:
                while True:

                    if self.stop_rec.is_set():
                        break

                    if self.resume_rec.is_set():
                        PAUSE = 0
                        for interval in secondary_buffer:
                            buffer.deque.append(interval)
                        AudioBuffer.resume(offset=int(len(secondary_buffer)*INTERVAL_DURATION))
                        self.resume_rec = threading.Event()
                        print("resuming")

                    _data = r.record(numframes=int(SAMPLERATE*INTERVAL_DURATION))

                    # if AudioBuffer.inactive:
                    #     sleep(INTERVAL_DURATION)
                    #     continue

                    data_tensor = torch.from_numpy(_data).reshape((2, -1))

                    if data_tensor.size(0) > 1:
                        data_tensor = data_tensor.mean(dim=0, keepdim=True)

                    if SAMPLERATE != 16000:
                        data_tensor = resampler(data_tensor)

                    speech_prob = model(data_tensor, 16000).item()
                    # print(f"prob: {speech_prob};    PAUSE: {PAUSE}")

                    if speech_prob < 0.5:
                        PAUSE += INTERVAL_DURATION
                    else:
                        PAUSE = 0
                        if AudioBuffer.inactive and self.resume_on_detected_voice:
                            AudioBuffer.resume()

                    if AudioBuffer.inactive:
                        secondary_buffer.update(_data, speech_prob)
                        sleep(min(INTERVAL_DURATION, 0.05))
                        continue

                    if PAUSE > 5:
                        print("pausing")
                        # AudioBuffer.inactive = True
                        # screenshot.ImageTempStorage.inactive = True
                        # AudioBuffer.last_active_date = datetime.now()
                        AudioBuffer.pause()
                        continue

                    buffer.update(_data, speech_prob)

        except KeyboardInterrupt:
            pass
        finally:
            AudioBuffer.inactive = False
            sf.write(file="audiobuffer.mp3", data=buffer.data, samplerate=SAMPLERATE)
