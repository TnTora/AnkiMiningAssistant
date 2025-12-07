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

from typing import overload, Literal
from collections.abc import Iterator, Generator, Iterable
from util.custom_typings import AudioInputDevice

from util import screenshot
from util import sockets
from util.database import audiodb, AudioSettings, GeneralSettings, sessionsdb

# TODO: add recording backend option in audio settings
if False:
    from . import audio_backend_sd as audio_backend
    recordingThread = audio_backend.recordingThreadSD
    get_audio_inputs = audio_backend.get_audio_inputs_sd
else:
    from . import audio_backend_sc as audio_backend
    # from .recorder_sc import recordingThreadSC, get_audio_inputs_sc
    recordingThread = audio_backend.recordingThreadSC
    get_audio_inputs = audio_backend.get_audio_inputs_sc

if sys.platform == "darwin":
    from util.AggregateDevice import isloopback
    def _isloopback(audio_input):
        return isloopback(audio_input.id)
else:
    def _isloopback(audio_input):
        return audio_input.isloopback

import logging

logger = logging.getLogger("app_logger")

monitoringAudio = None
# audio_input: "AudioInputDevice | None" = None
# buffer: "AudioBuffer | None" = None
# secondary_buffer: "AudioBuffer | None" = None
buffers: dict[str, "AudioBuffer"] = {}
record_audio_buffer: recordingThread | None = None

model = load_silero_vad(onnx=True)
resampler = torchaudio.transforms.Resample(AudioSettings.samplerate, 16000)


class AudioInterval:
    __slots__ = ["data", "vad", "timestamp"]

    def __init__(self, data: np.ndarray, vad: float | None = None, timestamp: float | None = None) -> None:
        self.data: np.ndarray = data
        self.vad: float = vad
        self.timestamp: float = timestamp or time()


class InactiveInterval:
    __slots__ = ["start_time", "end_time"]

    def __init__(self, start_time: datetime, end_time: datetime | None = None) -> None:
        self.start_time: datetime = start_time
        self.end_time: datetime | None = end_time


class AudioBuffer:

    storage_time_limit: timedelta = GeneralSettings.storage_time_limit
    inactive_intervals: list[InactiveInterval] = []
    inactive = True
    total_offset = timedelta(seconds=0)

    def __init__(self, channels: int=2, max_time: float | None = None, *, is_primary: bool = False) -> None:
        self.max_time: float = max_time or AudioBuffer.storage_time_limit.total_seconds()
        max_intervals = int(self.max_time // AudioSettings.interval_duration)+1
        self.deque: deque[AudioInterval] = deque(maxlen=max_intervals)
        self.channels: int = channels
        self.is_primary: bool = is_primary
        if self.is_primary:
            self.load_from_db()
            if self.inactive_intervals:
                screenshot.ImageTempStorage.last_active_date = self.inactive_intervals[-1].start_time
                sockets.LinesTempStorage.last_active_date = self.inactive_intervals[-1].start_time

    def load_from_db(self) -> None:
        for data, vad, timestamp in audiodb.load_buffer_intervals():
            self.update(data, vad, timestamp)
        for start, end in audiodb.load_inactive_intervals():
            start_time = datetime.fromtimestamp(start)
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

    def update(self, new_audio: np.ndarray, new_vad: float, timestamp: float | None = None) -> None:
        self.deque.append(AudioInterval(data=new_audio, vad=new_vad, timestamp=timestamp))

    def __iter__(self) -> Iterator[AudioInterval]:
        return self.deque.__iter__()

    def __getitem__(self, index: int) -> AudioInterval:
        return self.deque[index]

    def __len__(self) -> int:
        return self.deque.__len__()

    @staticmethod
    def get_db_channels() -> int | None:
        """Returns channels number for audio in db."""
        first_interval = next(audiodb.load_buffer_intervals(), None)
        if first_interval is None:
            return None
        try:
            prev_channels = first_interval[0].shape[1]
        except IndexError:
            prev_channels = 1
        return prev_channels

    def data(self, start_idx: int = 0, end_idx: int | None = None) -> np.ndarray:
        end_idx = end_idx or len(self.deque)

        data = np.concatenate(
            [interval.data for interval in self.slice_(start_idx, end_idx)],
            axis=0,
        )

        return data

    def get_data_in_blocks(self, blocksize: int, starting_idx: int = 0, frozen_deque=None) -> Generator[tuple[np.ndarray, int], None, None]:
        leftover_array: np.ndarray = np.empty((0, self.channels))
        interval_idx: int = starting_idx

        if frozen_deque is not None:
            intervals: Iterator[AudioInterval] = islice(frozen_deque, starting_idx, None)
        else:
            intervals: Iterator[AudioInterval] = self.slice_(start_idx=starting_idx, copy=True)


        for interval in intervals:
            start_idx = blocksize-len(leftover_array)
            leftover_array = np.append(leftover_array, interval.data[0:start_idx], axis=0)
            result, remainder = divmod(len(interval.data)-start_idx, blocksize)
            end_idx = start_idx + int(result*blocksize)  # int(AudioSettings.samplerate * AudioSettings.interval_duration)

            if len(leftover_array) == blocksize:
                yield leftover_array, interval_idx
                leftover_array = np.empty((0, self.channels))
            else:
                # if blocksize > len(interval.data) the contents of the interval have already been appended
                interval_idx += 1
                continue

            for i in range(start_idx, end_idx, blocksize):
                yield interval.data[i:i+blocksize], interval_idx

            interval_idx += 1

            if remainder > 0:
                leftover_array = interval.data[end_idx:]
                if interval_idx == len(self):
                    yield leftover_array, interval_idx

    def slice_(self, start_idx: int | None = None, end_idx: int | None = None, *, copy: bool = False) -> Iterator[AudioInterval]:
        if copy:
            return islice(self.deque.copy(), start_idx, end_idx)
        return islice(self.deque, start_idx, end_idx)

    @overload
    def copy_slice(self, start_idx: int | None = None, end_idx: int | None = None, *, to_list: Literal[True]) -> list[AudioInterval]: ...

    @overload
    def copy_slice(self, start_idx: int | None = None, end_idx: int | None = None, *, to_list: Literal[False]) -> deque[AudioInterval]: ...

    @overload
    def copy_slice(self, start_idx: int | None = None, end_idx: int | None = None) -> deque[AudioInterval]: ...

    def copy_slice(self, start_idx: int | None = None, end_idx: int | None = None, *, to_list: bool = False) -> Iterable[AudioInterval]:
        if to_list:
            # TODO: Test performance vs indexing deque in manual_update_note
            return list(self.slice_(start_idx, end_idx))
        return deque(self.slice_(start_idx, end_idx))
        # return buffer_copy

    @classmethod
    def get_total_offset(cls) -> timedelta:
        offset = timedelta(seconds=0)

        for interval in cls.inactive_intervals:
            if interval.end_time is None:
                continue
            offset += interval.end_time - interval.start_time

        return offset

    @classmethod
    def pause(cls) -> None:
        if cls.inactive:
            return
        cls.inactive = True
        screenshot.ImageTempStorage.inactive = True
        offset = timedelta(seconds=0)
        remove_up_to = 0
        curr_time = datetime.now()

        screenshot.ImageTempStorage.last_active_date = curr_time
        sockets.LinesTempStorage.last_active_date = curr_time

        for interval in reversed(cls.inactive_intervals):

            if curr_time - interval.end_time - offset > cls.storage_time_limit:
                remove_up_to = cls.inactive_intervals.index(interval) + 1
                break

            offset += interval.end_time - interval.start_time

        cls.total_offset = offset

        del cls.inactive_intervals[:remove_up_to]

        cls.inactive_intervals.append(InactiveInterval(start_time=datetime.now()))

    @classmethod
    def resume(cls, offset_sec: float = 0) -> None:
        offset = timedelta(seconds=offset_sec)
        cls.inactive = False
        screenshot.ImageTempStorage.inactive = False
        screenshot.ImageTempStorage.last_active_date = None
        sockets.LinesTempStorage.last_active_date = None
        if cls.inactive_intervals and cls.inactive_intervals[-1].end_time is None:
            cls.inactive_intervals[-1].end_time = datetime.now() - offset

    @classmethod
    def get_timing_adjustment(cls, final_time: datetime, line_time: datetime, *, allow_inactive: bool = False) -> timedelta | None:
        offset = timedelta(seconds=0)

        for interval in reversed(cls.inactive_intervals):
            if interval.start_time > final_time:
                continue
            if interval.end_time and final_time < interval.end_time:
                offset += interval.end_time - final_time
                continue

            if interval.end_time is None:
                if interval.start_time < line_time:
                    return None
                continue

            if interval.start_time < line_time < interval.end_time:
                if allow_inactive:
                    offset += interval.end_time - line_time
                    break
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
    ) -> tuple[deque[AudioInterval] | str | None, int | None, int | None]:

        line_start = None
        line_end = None

        if AudioBuffer.inactive:
            curr_time = AudioBuffer.inactive_intervals[-1].start_time
        else:
            curr_time = datetime.now()

        if curr_time - line_time - AudioBuffer.total_offset > AudioBuffer.storage_time_limit:
            logger.info("Line outside Buffer scope")
            return None, None, None

        data_copy = self.copy_slice()

        timing_adjustment = AudioBuffer.get_timing_adjustment(curr_time, line_time)

        if timing_adjustment is None:
            logger.info("No audio at line timestamp")
            return None, None, None

        if next_line_time is not None:
            line_audio_length = (next_line_time - line_time) - AudioBuffer.get_timing_adjustment(next_line_time, line_time)  # ty:ignore[unsupported-operator]
        else:
            line_end = len(data_copy)

        line_start = len(data_copy) - int(((curr_time - line_time) - timing_adjustment).total_seconds() // AudioSettings.interval_duration)

        if line_end is None:
            line_end = line_start + int(line_audio_length.total_seconds() // AudioSettings.interval_duration)

        last_active_interval = line_end

        j: int = line_start + 1
        for i in islice(data_copy, line_start+1, line_end):
            j += 1
            if i.vad > AudioSettings.vad_threshold:
                last_active_interval = j

        padding: int = int((AudioSettings.padding / 1000) / AudioSettings.interval_duration)
        line_start: int = max(line_start - padding, 0)
        line_end: int = min(last_active_interval + padding, line_end)

        if save_path:
            with sf.SoundFile(file=save_path, mode="w", channels=self.channels, samplerate=AudioSettings.samplerate) as f:
                for interval in islice(data_copy, line_start, line_end):
                    f.write(interval.data)
            return save_path, line_start, line_end

        return data_copy, line_start, line_end


class recordAudioBuffer(threading.Thread):

    def __init__(self, audio_input: AudioInputDevice) -> None:
        super().__init__()
        self.stop_rec = threading.Event()
        self.resume_rec = threading.Event()
        self.PAUSE = 0
        self.audio_input: AudioInputDevice = audio_input

    def stop_recording(self) -> None:
        self.stop_rec.set()
        logger.info("Stop monitoring")

    def resume_recording(self) -> None:
        self.PAUSE = 0
        if AudioBuffer.inactive:
            self.resume_rec.set()

    def run(self) -> None:
        buffer: AudioBuffer = buffers["primary"]
        secondary_buffer: AudioBuffer = buffers["secondary"]

        self.PAUSE = 0
        AudioBuffer.resume()

        record_worker = recordingThread(self.audio_input)
        record_worker.start()

        data_queue = record_worker.queue
        record_worker.recording_started.wait()
        logger.info("Start monitoring")

        while True:

            if self.stop_rec.is_set():
                AudioBuffer.pause()
                record_worker.stop_recording()
                break

            if self.resume_rec.is_set():
                buffer.deque.extend(secondary_buffer.deque)
                AudioBuffer.resume(offset_sec=len(secondary_buffer)*AudioSettings.interval_duration)
                self.resume_rec = threading.Event()
                logger.info("Resume monitoring")

            _data = data_queue.get()

            data_tensor = torch.from_numpy(_data).reshape((self.audio_input.channels, -1))

            if data_tensor.size(0) > 1:
                data_tensor = data_tensor.mean(dim=0, keepdim=True)

            if AudioSettings.samplerate != 16000:  # noqa: PLR2004
                data_tensor = resampler(data_tensor)

            speech_prob = model(data_tensor, 16000).item()

            if speech_prob < AudioSettings.vad_threshold and not AudioBuffer.inactive:
                self.PAUSE += 1
            else:
                self.PAUSE = 0
                if AudioBuffer.inactive and AudioSettings.resume_on_detected_voice:
                    AudioBuffer.resume()

            # print(f"prob: {speech_prob};    self.PAUSE: {self.PAUSE}; {datetime.now().strftime('%H_%M_%S')}")
            # logger.debug("PAUSE: %s (%s); speech_prob: %s", self.PAUSE, self.PAUSE*AudioSettings.interval_duration, speech_prob)

            if AudioBuffer.inactive:
                secondary_buffer.update(_data, speech_prob)
                continue

            if AudioSettings.pause_threshold < self.PAUSE*AudioSettings.interval_duration and not sessionsdb.current_session["continuous_recording"]:
                logger.info("Pause monitoring")
                # print(f"{datetime.now().strftime('%H_%M_%S')}: {self.PAUSE = }, {self.PAUSE*AudioSettings.interval_duration}")
                secondary_buffer.deque.clear()
                AudioBuffer.pause()
                continue

            buffer.update(_data, speech_prob)
