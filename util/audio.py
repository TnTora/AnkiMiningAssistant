import threading
import torch
import torchaudio
import sys
import numpy as np
import soundcard as sc
import soundfile as sf
from silero_vad import load_silero_vad
from time import time
from datetime import datetime, timedelta
from collections import deque
from itertools import islice

from util import screenshot
from util.database import audiodb, AudioSettings, GeneralSettings, sessionsdb

if sys.platform == "darwin":
    from util.AggregateDevice import isloopback
    def _isloopback(mic):
        return isloopback(mic.id)
else:
    def _isloopback(mic):
        return mic.isloopback

monitoringAudio = None
mic = None
buffer = None
secondary_buffer = None
record_audio_buffer = None

model = load_silero_vad()
resampler = torchaudio.transforms.Resample(AudioSettings.samplerate, 16000)


class AudioInterval:

    def __init__(self, data, vad=None, timestamp=None) -> None:
        self.data = data
        self.vad = vad
        self.timestamp = timestamp or time()


class InactiveInterval:

    def __init__(self, start_time, end_time=None):
        self.start_time = start_time
        self.end_time = end_time


class AudioBuffer:

    storage_time_limit = GeneralSettings.storage_time_limit
    inactive_intervals = []
    inactive = True
    total_offset = timedelta(seconds=0)

    def __init__(self, channels=2, max_time=None, *, is_primary=False):
        self.max_time = max_time or AudioBuffer.storage_time_limit.total_seconds()
        max_intervals = int(self.max_time // AudioSettings.interval_duration)+1
        self.deque = deque(maxlen=max_intervals)
        self.channels = channels
        self.is_primary = is_primary
        if self.is_primary:
            self.load_from_db()

    def load_from_db(self):
        for data, vad, timestamp in audiodb.load_buffer_intervals():
            self.update(data, vad, timestamp)
        for start, end in audiodb.load_inactive_intervals():
            start_time = datetime.fromtimestamp(start)
            # end_time = end if not end else datetime.fromtimestamp(end)
            try:
                end_time = datetime.fromtimestamp(end)
            except TypeError:
                end_time = None
            self.inactive_intervals.append(
                InactiveInterval(
                    start_time=start_time,
                    end_time=end_time
                )
            )

    def update(self, new_audio, new_vad, timestamp=None):
        self.deque.append(AudioInterval(data=new_audio, vad=new_vad, timestamp=timestamp))

    def __iter__(self):
        return self.deque.__iter__()

    def __getitem__(self, index):
        return self.deque[index]

    def __len__(self):
        return self.deque.__len__()

    def data(self, start_idx=0, end_idx=None):
        end_idx = end_idx or len(self.deque)

        data = np.concatenate(
            [interval.data for interval in self.slice_(start_idx, end_idx)],
            axis=0,
        )

        return data

    @staticmethod
    def get_data_in_blocks(audio_buffer, blocksize: int, starting_idx: int = 0):
        leftover_array = np.empty((0, audio_buffer.channels))
        interval_idx = starting_idx

        for interval in audio_buffer.slice_(start_idx=starting_idx):
            start_idx = blocksize-len(leftover_array)
            leftover_array = np.append(leftover_array, interval.data[0:start_idx], axis=0)
            result, remainder = divmod(len(interval.data)-start_idx, blocksize)
            end_idx = start_idx + int(result*blocksize)  # int(AudioSettings.samplerate * AudioSettings.interval_duration)

            if len(leftover_array) == blocksize:
                yield leftover_array, interval_idx

            for i in range(start_idx, end_idx, blocksize):
                yield interval.data[i:i+blocksize], interval_idx

            interval_idx += 1

            if remainder > 0:
                leftover_array = interval.data[end_idx:]
                if interval_idx == len(audio_buffer):
                    yield leftover_array, interval_idx
            else:
                leftover_array = np.empty((0, audio_buffer.channels))

    def slice_(self, start_idx=None, end_idx=None, step=None):
        return islice(self.deque, start_idx, end_idx, step)

    def copy_slice(self, start_idx=None, end_idx=None, step=None, *, deque_to_list=False):
        buffer_copy = AudioBuffer(channels=self.channels, max_time=self.max_time, is_primary=False)
        if deque_to_list:
            # TODO: Test performance vs indexing deque in manual_update_note
            buffer_copy.deque = list(self.slice_(start_idx, end_idx, step))
        else:
            buffer_copy.deque = deque(self.slice_(start_idx, end_idx, step))
        return buffer_copy

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
        if cls.inactive:
            return
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

        cls.total_offset = offset

        del cls.inactive_intervals[:remove_up_to]

        cls.inactive_intervals.append(InactiveInterval(start_time=datetime.now()))

    @classmethod
    def resume(cls, offset=0):
        offset = timedelta(seconds=offset)
        cls.inactive = False
        screenshot.ImageTempStorage.inactive = False
        if cls.inactive_intervals and cls.inactive_intervals[-1].end_time is None:
            cls.inactive_intervals[-1].end_time = datetime.now() - offset

    @classmethod
    def get_timing_adjustment(cls, curr_time, line_time):
        offset = timedelta(seconds=0)

        for interval in reversed(cls.inactive_intervals):

            if interval.end_time is None:
                if interval.start_time < line_time:
                    return None
                continue

            if interval.start_time < line_time < interval.end_time:
                return None

            if line_time > interval.end_time:
                break

            offset += interval.end_time - interval.start_time

        return offset

    def extract_line_audio(
        self,
        line_time: datetime,
        next_line_time: datetime | None = None,
        save_path: str | None = None,
    ) -> tuple[list | str | None, int | None, int | None]:

        line_start = None
        line_end = None

        if AudioBuffer.inactive:
            curr_time = AudioBuffer.inactive_intervals[-1].start_time
        else:
            curr_time = datetime.now()

        if curr_time - line_time - AudioBuffer.total_offset > AudioBuffer.storage_time_limit:
            print("Outside Buffer scope")
            return None, None, None

        data_copy = self.copy_slice()

        if next_line_time:
            line_audio_length = next_line_time - line_time
        else:
            line_end = len(data_copy)

        timing_adjustment = AudioBuffer.get_timing_adjustment(curr_time, line_time)

        if timing_adjustment is None:
            # TODO: log
            print("no audio at line timestamp")
            return None, None, None

        line_start = len(data_copy) - int(((curr_time - line_time) - timing_adjustment).total_seconds() // AudioSettings.interval_duration)

        if line_end is None:
            line_end = line_start + int(line_audio_length.total_seconds() // AudioSettings.interval_duration)

        last_active_interval = line_end

        j = line_start + 1
        for i in islice(data_copy.deque, line_start+1, line_end):
            j += 1
            if i.vad > AudioSettings.vad_threshold:
                last_active_interval = j

        padding = 10
        line_start = max(line_start - padding, 0)
        line_end = min(last_active_interval + padding, line_end)

        if save_path:
            with sf.SoundFile(file=save_path, mode="w", channels=self.channels, samplerate=AudioSettings.samplerate) as f:
                for interval in islice(data_copy.deque, line_start, line_end):
                    f.write(interval.data)
            return save_path, line_start, line_end

        return data_copy, line_start, line_end


def get_mics():
    mikes = sc.all_microphones(include_loopback=True)
    loopbacks = []
    for i in range(len(mikes)):
        loopback = _isloopback(mikes[i])
        if loopback:
            loopbacks.append(i)
        stored_in_db = mikes[i].name == AudioSettings.mic
        if stored_in_db:
            return mikes, i
    if loopbacks:
        return mikes, loopbacks[0]
    return mikes, None


class recordAudioBuffer(threading.Thread):

    def __init__(self):
        super().__init__()
        self.stop_rec = threading.Event()
        self.resume_rec = threading.Event()

    def stop_recording(self):
        self.stop_rec.set()

    def resume_recording(self):
        self.resume_rec.set()

    def run(self):  # noqa: C901
        PAUSE = 0
        AudioBuffer.resume()
        with mic.recorder(samplerate=AudioSettings.samplerate) as r:
            while True:

                if self.stop_rec.is_set():
                    AudioBuffer.pause()
                    break

                if self.resume_rec.is_set():
                    PAUSE = 0
                    for interval in secondary_buffer:
                        # print(f"appending interval: {interval.timestamp}")
                        buffer.deque.append(interval)
                    AudioBuffer.resume(offset=len(secondary_buffer)*AudioSettings.interval_duration)
                    self.resume_rec = threading.Event()
                    print("resuming")

                _data = r.record(numframes=int(AudioSettings.samplerate*AudioSettings.interval_duration))

                data_tensor = torch.from_numpy(_data).reshape((2, -1))

                if data_tensor.size(0) > 1:
                    data_tensor = data_tensor.mean(dim=0, keepdim=True)

                if AudioSettings.samplerate != 16000:  # noqa: PLR2004
                    data_tensor = resampler(data_tensor)

                speech_prob = model(data_tensor, 16000).item()

                if speech_prob < AudioSettings.vad_threshold and not AudioBuffer.inactive:
                    PAUSE += AudioSettings.interval_duration
                else:
                    PAUSE = 0
                    if AudioBuffer.inactive and AudioSettings.resume_on_detected_voice:
                        AudioBuffer.resume()

                # print(f"prob: {speech_prob};    PAUSE: {PAUSE}; {datetime.now().strftime('%H_%M_%S')}")

                if AudioBuffer.inactive:
                    secondary_buffer.update(_data, speech_prob)
                    continue

                if AudioSettings.pause_threshold < PAUSE and not sessionsdb.current_session["continuous_recording"]:
                    print("pausing")
                    secondary_buffer.deque.clear()
                    AudioBuffer.pause()
                    continue

                buffer.update(_data, speech_prob)
