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


monitoringAudio = None
SAMPLERATE = 44100
INTERVAL_DURATION = 512/16000  # 0.1
mic = None
buffer = None
record_audio_buffer = None

resampler = torchaudio.transforms.Resample(SAMPLERATE, 16000)


class AudioBuffer:

    storage_time_limit = timedelta(minutes=0, seconds=20)

    def __init__(self, channels=2):
        self.data = np.zeros((1, channels))
        self.vad_res = np.zeros((1, 1))
        self.channels = channels
        self.storage_full = False
        self.last_active_date = datetime.min
        self.restart_date = datetime.max
        self.inactive = False

    def update(self, new_data, new_vad_res: float):
        if self.storage_full:
            self.data = np.delete(self.data, slice(0, int(SAMPLERATE*INTERVAL_DURATION)), axis=0)
            self.vad_res = np.delete(self.vad_res, slice(0, int(SAMPLERATE*INTERVAL_DURATION)), axis=0)
            self.data = np.concatenate((self.data, new_data))
            self.vad_res = np.concatenate((self.vad_res, np.full((new_data.shape[0], 1), new_vad_res)))
            return

        audio_length = timedelta(seconds=self.data.shape[0] / SAMPLERATE)

        if audio_length > self.storage_time_limit:
            self.storage_full = True
            self.data = np.delete(self.data, slice(0, int(SAMPLERATE*INTERVAL_DURATION)), axis=0)
            self.vad_res = np.delete(self.vad_res, slice(0, int(SAMPLERATE*INTERVAL_DURATION)), axis=0)

        self.data = np.concatenate((self.data, new_data))
        self.vad_res = np.concatenate((self.vad_res, np.full((new_data.shape[0], 1), new_vad_res)))

    def extract_line_audio(
        self,
        line_time,
        next_line_time=None,
    ):
        line_start = None
        line_end = None

        if self.inactive:
            curr_time = self.last_active_date
        else:
            curr_time = datetime.now()

        data_copy = np.copy(self.data)

        if next_line_time:
            line_audio_length = next_line_time - line_time
        else:
            line_end = data_copy.shape[0]

        if curr_time - self.restart_date > self.storage_time_limit:
            self.last_active_date = datetime.min
            self.restart_date = datetime.max
            timing_adjustment = timedelta(seconds=0)
        elif line_time > self.restart_date:
            timing_adjustment = timedelta(seconds=0)
        else:
            timing_adjustment = self.restart_date - self.last_active_date

        line_start = data_copy.shape[0] - ((curr_time - line_time) - timing_adjustment).total_seconds()*SAMPLERATE

        if line_end is None:
            line_end = line_start + line_audio_length*SAMPLERATE

        data_copy = np.copy(data_copy[line_start:line_end, :])

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


model = load_silero_vad()
PLAYBACK = False


def monitorSystemAudio(widget, storage, info):
    global monitoringAudio
    PAUSE = 0
    resampler = torchaudio.transforms.Resample(SAMPLERATE, 16000)
    try:
        monitoringAudio = threading.Event()
        # storage.append(np.empty((0, mic.channels)))
        ACTIVE = False
        temp_data = np.empty((0, mic.channels))
        curr_time = None
        widget_item = None
        # widget.clear()
        NUMFRAMES = int(SAMPLERATE*INTERVAL_DURATION)
        with mic.recorder(samplerate=SAMPLERATE) as r:
            while True:
                if monitoringAudio.is_set():
                    monitoringAudio = None
                    break

                if PLAYBACK:
                    sleep(0.5)
                    continue

                _data = r.record(numframes=NUMFRAMES)

                data_tensor = torch.t(torch.from_numpy(_data))  # .reshape((2, -1))

                if data_tensor.size(0) > 1:
                    data_tensor = data_tensor.mean(dim=0, keepdim=True)

                if SAMPLERATE != 16000:
                    data_tensor = resampler(data_tensor)

                speech_prob = model(data_tensor, 16000).item()
                # print(f"prob: {speech_prob};    PAUSE: {PAUSE}")

                if PAUSE > 3:
                    PAUSE = 0
                    ACTIVE = False

                if PAUSE > 2:
                    temp_data = np.empty((0, mic.channels))

                temp_data = np.concatenate((temp_data, _data))

                if speech_prob < 0.5:
                    PAUSE += INTERVAL_DURATION
                    continue
                elif not ACTIVE:
                    PAUSE = 0
                    # temp_data = np.concatenate((temp_data, _data))
                    time = temp_data.shape[0]/SAMPLERATE
                    curr_time = datetime.now()
                    if len(storage) > 4:
                        del storage[0]
                        del info[0]
                    if time > 0.1:
                        storage.append(temp_data)
                        info.append(f"[{curr_time.hour}:{curr_time.minute}:{curr_time.second}] {round(time, 3)}")
                        widget.clear()
                        widget.addItems(info)
                        widget_item = widget.item(len(info)-1)
                        widget_item.setSelected(True)
                        ACTIVE = True
                        temp_data = np.empty((0, mic.channels))
                else:
                    PAUSE = 0
                    storage[-1] = np.concatenate((storage[-1], temp_data))
                    time = storage[-1].shape[0]/SAMPLERATE
                    if True:  # time % 0.25 == 0:
                        info[-1] = f"[{curr_time.hour}:{curr_time.minute}:{curr_time.second}] {round(time, 3)}"
                        widget_item.setText(info[-1])
                    temp_data = np.empty((0, mic.channels))

                # if data is None:
                #     data = _data
                # else:
                #     data = np.concatenate((data, _data))
    except KeyboardInterrupt:
        pass


def startMonitoringAudio(widget, storage, info):
    if monitoringAudio is not None:
        monitoringAudio.set()
    else:
        thread = threading.Thread(
            target=monitorSystemAudio,
            args=(widget, storage, info))
        thread.start()


class recordAudioBuffer(threading.Thread):

    def __init__(self):
        super().__init__()
        self.stop_rec = threading.Event()

    def stop_recording(self):
        self.stop_rec.set()

    def run(self):
        try:
            PAUSE = 0
            with mic.recorder(samplerate=SAMPLERATE) as r:
                while True:

                    if self.stop_rec.is_set():
                        break

                    if buffer.inactive:
                        sleep(INTERVAL_DURATION)
                        continue

                    _data = r.record(numframes=int(SAMPLERATE*INTERVAL_DURATION))

                    data_tensor = torch.from_numpy(_data).reshape((2, -1))

                    if data_tensor.size(0) > 1:
                        data_tensor = data_tensor.mean(dim=0, keepdim=True)

                    if SAMPLERATE != 16000:
                        data_tensor = resampler(data_tensor)

                    speech_prob = model(data_tensor, 16000).item()
                    print(f"prob: {speech_prob};    PAUSE: {PAUSE}")

                    if speech_prob < 0.5:
                        PAUSE += INTERVAL_DURATION
                    else:
                        PAUSE = 0
                        buffer.inactive = False

                    if PAUSE > 5:
                        buffer.inactive = True
                        continue

                    buffer.update(_data, speech_prob)

        except KeyboardInterrupt:
            pass
        finally:
            buffer.inactive = False
            sf.write(file="audiobuffer.mp3", data=buffer.data, samplerate=SAMPLERATE)
