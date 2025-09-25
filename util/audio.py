import threading
import torch
import torchaudio
import numpy as np
import soundcard as sc
import soundfile as sf
from silero_vad import load_silero_vad
from time import sleep
from datetime import datetime
from util.AggregateDevice import isloopback


monitoringAudio = None
SAMPLERATE = 44100
mic = None


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
    INTERVAL_DURATION = 512/16000  # 0.1
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
