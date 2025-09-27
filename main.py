import sys
import soundcard as sc
import numpy as np

from PySide6.QtCore import (
    Qt,
    QRunnable,
    QThreadPool,
    Slot,
    QTimer
)
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QCheckBox,
    QComboBox,
    QLabel,
    QListWidget,
    QMainWindow,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QSlider,
    QSizePolicy
)

import util.util as util
from util.AggregateDevice import createAggregateDevice, destroyAggregateDevice
from util.anki import start_monitoring_anki
from util.mac import (
    getAllApps,
    getAS_Process,
    getAppWindows,
    getAppAXWindows,
    getAXWindowFromWindowInfo
)
from util.sockets import WebsocketManagerThread
import util.audio as audio
import util.screenshot as screenshot


class ConfirmationDialog(QDialog):
    def __init__(self, text):
        super().__init__()

        self.setWindowTitle("Confirm")

        QBtn = (
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        layout = QVBoxLayout()
        message = QLabel(text)
        layout.addWidget(message)
        layout.addWidget(self.buttonBox)
        self.setLayout(layout)


class Player_Worker(QRunnable):
    """Worker thread."""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self._data = None
        self.frames = None
        self._dataT = None
        self.step = 1000
        self.playing = False
        self.cursor = 0

    @Slot()
    def run(self):
        if self._data is None:
            return

        if int(self.cursor/self.step) == (int(self.frames/self.step)-1):
            self.cursor = 0

        with sc.default_speaker().player(samplerate=util.SAMPLERATE) as sp:
            for i in range(int(self.cursor/self.step), int(self.frames/self.step)):
                self.cursor = i*self.step
                if not self.playing:
                    util.PLAYBACK = False
                    break
                # print(f"{i}: [{i*step}:{(i+1)*step}]")
                # print(_dataT[i*500:(i+1)*500])
                # print("-"*20)
                temp = self._dataT[:, i*self.step:(i+1)*self.step]
                # temp = librosa.effects.time_stretch(temp, rate=2)
                # print(temp)
                sp.play(temp.T)

        self.playing = False
        self.main_window.play_button.setText("Play")

        if self.main_window.audio_monitoring and audio.monitoringAudio is None:
            audio.startMonitoringAudio(self.main_window.listwidget, self.main_window.audio_data, self.main_window.audio_info)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.apps = getAllApps()
        self.windows = None
        self.mikes, loop_idx = audio.get_mics()

        self.audio_data = []
        self.audio_info = []
        self.audio_monitoring = False

        self.setWindowTitle("miningVN")
        self.layout = QVBoxLayout()

        self.sessionLayout = QHBoxLayout()

        self.session_select = QComboBox()
        self.session_select.addItems(list(util.sessions.keys()))
        self.session_select.currentTextChanged.connect(self.set_session)
        self.sessionLayout.addWidget(self.session_select)

        self.reload_button = QPushButton("Reload")
        self.reload_button.released.connect(lambda: self.set_session(self.session_select.currentText()))
        self.sessionLayout.addWidget(self.reload_button)

        self.layout.addLayout(self.sessionLayout)

        self.app_sel_Layout = QHBoxLayout()

        self.app_sel_label = QLabel("App: ")
        self.app_sel_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self.app_sel_Layout.addWidget(self.app_sel_label)

        self.app_select = QComboBox()
        self.app_select.addItems([a.localizedName() for a in self.apps])
        self.app_select.currentIndexChanged.connect(self.set_app)
        self.app_sel_Layout.addWidget(self.app_select)

        self.app_refresh = QPushButton("Refresh")
        self.app_refresh.released.connect(self.refresh_app_list)
        self.app_refresh.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.app_sel_Layout.addWidget(self.app_refresh)

        self.layout.addLayout(self.app_sel_Layout)

        self.win_sel_Layout = QHBoxLayout()

        self.win_sel_label = QLabel("Win: ")
        self.win_sel_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self.win_sel_Layout.addWidget(self.win_sel_label)

        self.window_select = QComboBox()
        self.window_select.currentIndexChanged.connect(self.set_window)
        self.win_sel_Layout.addWidget(self.window_select)

        self.layout.addLayout(self.win_sel_Layout)

        self.mic_sel_Layout = QHBoxLayout()

        self.mic_sel_label = QLabel("Mic: ")
        self.mic_sel_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self.mic_sel_Layout.addWidget(self.mic_sel_label)

        self.mic_select = QComboBox()
        self.mic_select.addItems([f"{mic}" for mic in self.mikes])
        self.mic_select.currentIndexChanged.connect(self.set_mic)
        if loop_idx is not None:
            self.mic_select.setCurrentIndex(loop_idx)
        self.mic_sel_Layout.addWidget(self.mic_select)

        self.layout.addLayout(self.mic_sel_Layout)

        self.use_audio_button = QCheckBox("Use audio button")
        self.use_audio_button.stateChanged.connect(self.set_use_audio_button)
        # self.use_audio_button.checkStateChanged.connect(self.set_use_audio_button)
        self.layout.addWidget(self.use_audio_button)

        self.buttonHlayout = QHBoxLayout()

        self.rec_screen_button = QPushButton("Screenshot")
        self.rec_screen_button.released.connect(util.recordHotKeyScreenshot)
        self.buttonHlayout.addWidget(self.rec_screen_button)

        self.rec_audio_button = QPushButton("Audio")
        self.rec_audio_button.released.connect(self.getAudio)
        self.buttonHlayout.addWidget(self.rec_audio_button)

        self.rec_both_button = QPushButton("Both")
        self.rec_both_button.released.connect(self.getBoth)
        self.buttonHlayout.addWidget(self.rec_both_button)

        self.layout.addLayout(self.buttonHlayout)

        self.playerHlayout = QHBoxLayout()

        self.play_button = QPushButton("Play")
        self.play_button.released.connect(self.playAudio)
        self.playerHlayout.addWidget(self.play_button)

        self.rate_select = QComboBox()
        self.rate_select.addItems(["1", "1.25", "1.5", "2"])
        # self.rate_select.currentIndexChanged.connect(self.set_rate)
        self.playerHlayout.addWidget(self.rate_select)

        self.audio_slider = QSlider()
        self.audio_slider.setMinimum(0)
        self.audio_slider.setMaximum(10000)
        self.audio_slider.setValue(0)
        self.audio_slider.setSingleStep(1)
        self.audio_slider.setOrientation(Qt.Horizontal)
        self.audio_slider.sliderMoved.connect(self.slider_moved)
        self.playerHlayout.addWidget(self.audio_slider)

        self.layout.addLayout(self.playerHlayout)

        self.listwidget = QListWidget()
        # self.listwidget.addItems(["test 1", "test 2", "test 3"])
        self.listwidget.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.listwidget.setAlternatingRowColors(True)
        self.listwidget.itemSelectionChanged.connect(self.changedSelection)

        self.monitoring_button = QPushButton("Start Monitoring Audio")
        self.monitoring_button.released.connect(self.audioMonitor)
        self.layout.addWidget(self.monitoring_button)

        self.layout.addWidget(self.listwidget)

        self.layout.addWidget(QLabel("Last Anki Note"))

        self.last_note_info = QLabel("Word:\nSentence:")
        self.layout.addWidget(self.last_note_info)

        self.set_session(self.session_select.currentText())

        widget = QWidget()
        widget.setLayout(self.layout)
        self.setCentralWidget(widget)

        util.signals.confirm.connect(self.openConfirmationDialog)

        self.threadpool = QThreadPool()
        self.player = Player_Worker(self)
        self.player.setAutoDelete(False)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.updateSlider)
        self.timer.start(500)

        start_monitoring_anki(self.update_anki_note_info)

    def update_anki_note_info(self, info):
        self.last_note_info.setText(info)

    def updateSlider(self):
        if self.player._data is None:
            return
        # print(f"timeout value: {int(self.player.cursor/self.player.frames*10000)}, cursor: {self.player.cursor}, frames: {self.player.frames}")
        self.audio_slider.setValue(int(self.player.cursor/self.player.frames*10000))

    def refresh_app_list(self):
        self.apps = getAllApps()
        self.app_select.clear()
        self.app_select.addItems([a.localizedName() for a in self.apps])

    def set_session(self, key):
        if not key:
            return
        print(f"session: {util.sessions[key]}")
        self.app_select.currentIndexChanged.disconnect(self.set_app)
        self.window_select.currentIndexChanged.disconnect(self.set_window)
        try:
            self.apps = getAllApps()
            self.app_select.clear()
            self.app_select.addItems([a.localizedName() for a in self.apps])
            self.app_select.setCurrentIndex(-1)
            for i in range(len(self.apps)):
                if self.apps[i].localizedName() == util.sessions[key]["AppName"]:
                    self.app_select.setCurrentIndex(i)
                    break
            if self.app_select.currentIndex() < 0:
                raise Exception(f"{util.sessions[key]["AppName"]} not running")
            self.set_app(self.app_select.currentIndex())
            self.window_select.setCurrentIndex(-1)
            for i in range(len(self.windows)):
                if self.windows[i]["kCGWindowName"] == util.sessions[key]["WindowTitle"]:
                    self.window_select.setCurrentIndex(i)
                    break
            if self.window_select.currentIndex() < 0:
                raise Exception(f"{util.sessions[key]["WindowTitle"]} window not found")
            self.set_window(self.window_select.currentIndex())
        except Exception as e:
            print(e)
        finally:
            self.app_select.currentIndexChanged.connect(self.set_app)
            self.window_select.currentIndexChanged.connect(self.set_window)

    def set_app(self, index):
        print(f"self.apps[index]: {self.apps[index]}")
        util.app = self.apps[index]
        util.proc = getAS_Process(util.se, util.app)
        self.windows = getAppWindows(self.apps[index])
        self.window_select.clear()
        self.window_select.addItems([w["kCGWindowName"] for w in self.windows])

    def set_window(self, index):
        try:
            print(f"self.windows[index]: {self.windows[index]}")
            util.win = self.windows[index]
            util.selected_win_AX = getAXWindowFromWindowInfo(getAppAXWindows(util.app), self.windows[index])
        except Exception as e:
            print(e)

    def set_mic(self, index):
        audio.mic = self.mikes[index]
        if audio.buffer is None or audio.buffer.channels != audio.mic.channels:
            audio.buffer = audio.AudioBuffer(channels=audio.mic.channels)

    def set_use_audio_button(self, state):
        print(f"state: {state}")
        if state:
            util.use_button = True
        else:
            util.use_button = False

    def audioMonitor(self):
        if not self.audio_monitoring:
            self.monitoring_button.setText("Stop Monitoring Audio")
            self.audio_monitoring = True
        else:
            self.monitoring_button.setText("Start Monitoring Audio")
            self.audio_monitoring = False
        # audio.startMonitoringAudio(self.listwidget, self.audio_data, self.audio_info)
        if audio.record_audio_buffer is None:
            audio.record_audio_buffer = audio.recordAudioBuffer()
            audio.record_audio_buffer.start()
        else:
            audio.record_audio_buffer.stop_recording()
            audio.record_audio_buffer.join()
            audio.record_audio_buffer = None

        if screenshot.screenshot_manager is None:
            screenshot.screenshot_manager = screenshot.ScreenshotManager(interval=1)
            screenshot.screenshot_manager.start()
        else:
            screenshot.screenshot_manager.stop_recording()
            screenshot.screenshot_manager.join()
            screenshot.screenshot_manager = None

    def getAudio(self):
        if self.audio_monitoring:
            sel_indeces = sorted([x.row() for x in self.listwidget.selectedIndexes()])
            # print(self.audio_data)
            # print(sel_indeces)
            util.recordHotKeyAudio(data=[self.audio_data[i] for i in sel_indeces])
        else:
            util.recordHotKeyAudio()

    def getBoth(self):
        if self.audio_monitoring:
            sel_indeces = sorted([x.row() for x in self.listwidget.selectedIndexes()])
            util.recordHotKeyBoth(data=[self.audio_data[i] for i in sel_indeces])
        else:
            util.recordHotKeyBoth()

    def openConfirmationDialog(self, data):
        confirmD = ConfirmationDialog(data)
        if confirmD.exec():
            util.confirmed = True
        else:
            util.confirmed = False
        util.condition.set()

    def playAudio(self):
        if self.player._data is None:
            sel_indeces = sorted([x.row() for x in self.listwidget.selectedIndexes()])
            self.player._data = np.concatenate([self.audio_data[i] for i in sel_indeces])
            self.player.frames = self.player._data.shape[0]
            self.player._dataT = self.player._data.T
            self.player.cursor = 0
        if self.player.playing:
            self.play_button.setText("Play")
            self.player.playing = False
            # util.PLAYBACK = False
        else:
            self.play_button.setText("Pause")
            self.player.playing = True
            # util.PLAYBACK = True
            if audio.monitoringAudio is not None:
                audio.monitoringAudio.set()
            self.threadpool.start(self.player)

    def slider_moved(self):
        if self.player._data is None:
            return
        self.player.playing = False
        self.player.cursor = int((self.audio_slider.value()/10000)*self.player.frames)

    def changedSelection(self):
        self.player._data = None
        self.player.frames = None
        self.player._dataT = None
        self.player.cursor = 0
        self.player.playing = False
        util.PLAYBACK = False


def main():
    createAggregateDevice()
    util.hotkeys.start()
    util.hotkeys.wait()
    ws_server = WebsocketManagerThread(ws_port=6678, listen_urls=["localhost:6677"])
    ws_server.start()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    if sys.platform == "darwin":
        print("darwon")
        window.raise_()
    app.exec()
    util.hotkeys.stop()
    destroyAggregateDevice()
    if audio.monitoringAudio is not None:
        audio.monitoringAudio.set()


if __name__ == "__main__":
    main()
