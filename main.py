import sys
import soundcard as sc
# import numpy as np
from datetime import datetime

from PySide6.QtCore import (
    Qt,
    QRunnable,
    QThreadPool,
    # Slot,
    QTimer,
)
from PySide6.QtWidgets import (
    QApplication,
    # QTextEdit,
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
    QSizePolicy,
)

from util.AggregateDevice import createAggregateDevice, destroyAggregateDevice
from util.anki import start_monitoring_anki
from util.database import (
    settings,
    imagedb,
    audiodb,
    linedb,
    sessionsdb
)
from util.mac import (
    getAllApps,
    # getAS_Process,
    getAppWindows,
    # getAppAXWindows,
    # getAXWindowFromWindowInfo
)
import util.sockets
import util.audio as audio
import util.screenshot as screenshot
import util.util as ut

# from settings_gui import SettingsWindow


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


class PlayerState:
    total_intervals = 0
    cursor = 0
    playing = False


class Player_Worker(QRunnable):
    """Worker thread."""

    def __init__(self):
        super().__init__()
        # self._data = None
        # self.frames = None
        # self._dataT = None
        # self.step = 1000

    def run(self):
        # if self._data is None:
        #     return

        # if int(self.cursor/self.step) == (int(self.frames/self.step)-1):
        #     self.cursor = 0

        if PlayerState.cursor == PlayerState.total_intervals:
            PlayerState.cursor = 0

        with sc.default_speaker().player(samplerate=settings.audio.samplerate, blocksize=83) as sp:
            # for i in range(int(self.cursor/self.step), int(self.frames/self.step)):
            #     self.cursor = i*self.step
            #     if not self.playing:
            #         audio.PLAYBACK = False
            #         break
            #     temp = self._dataT[:, i*self.step:(i+1)*self.step]
            #     # temp = librosa.effects.time_stretch(temp, rate=2)
            #     sp.play(temp.T)
            for interval in audio.buffer.slice_(start_idx=PlayerState.cursor):
                if not PlayerState.playing:
                    PlayerState.playing = False
                    break
                sp.play(interval.data)
                PlayerState.cursor += 1


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.apps = getAllApps()
        self.windows = None
        # self.sessions = sessionsdb.load_sessions()
        self.mikes, preferred_idx = audio.get_mics()

        self.audio_data = []
        self.audio_info = []
        self.av_monitoring = False

        self.setWindowTitle("miningVN")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()
        self.main_layout = QVBoxLayout()

        self.sessionLayout = QHBoxLayout()

        self.session_select = QComboBox()
        self.session_select.setEditable(True)
        self.session_select.addItems(list(sessionsdb.sessions_dict.keys()))
        self.session_select.currentTextChanged.connect(self.set_session)
        self.sessionLayout.addWidget(self.session_select)

        self.new_session_button = QPushButton("New")
        self.new_session_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.new_session_button.released.connect(self.add_session)
        self.sessionLayout.addWidget(self.new_session_button)

        self.main_layout.addLayout(self.sessionLayout)

        self.app_sel_Layout = QHBoxLayout()

        self.app_sel_label = QLabel("App: ")
        self.app_sel_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self.app_sel_Layout.addWidget(self.app_sel_label)

        self.app_select = QComboBox()
        self.app_select.addItems([a.localizedName() for a in self.apps])
        self.app_select.setCurrentIndex(-1)
        self.app_select.currentIndexChanged.connect(self.set_app)
        self.app_sel_Layout.addWidget(self.app_select)

        self.app_refresh = QPushButton("Refresh")
        self.app_refresh.released.connect(self.refresh_app_list)
        self.app_refresh.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.app_sel_Layout.addWidget(self.app_refresh)

        self.main_layout.addLayout(self.app_sel_Layout)

        self.win_sel_Layout = QHBoxLayout()

        self.win_sel_label = QLabel("Win: ")
        self.win_sel_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self.win_sel_Layout.addWidget(self.win_sel_label)

        self.window_select = QComboBox()
        self.window_select.currentIndexChanged.connect(self.set_window)
        self.win_sel_Layout.addWidget(self.window_select)

        self.main_layout.addLayout(self.win_sel_Layout)

        # Set session after creating app and window widgets since they are
        # used in set_session

        if settings.general.last_session:
            # print(list(sessionsdb.sessions_dict.keys()))
            # print(settings.general.last_session)
            # print(f"last idx: {list.index(list(sessionsdb.sessions_dict.keys()), settings.general.last_session)}")
            self.session_select.setCurrentIndex(list.index(list(sessionsdb.sessions_dict.keys()), settings.general.last_session))

        self.mic_sel_Layout = QHBoxLayout()

        self.mic_sel_label = QLabel("Mic: ")
        self.mic_sel_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self.mic_sel_Layout.addWidget(self.mic_sel_label)

        self.mic_select = QComboBox()
        self.mic_select.addItems([f"{mic}" for mic in self.mikes])
        self.mic_select.currentIndexChanged.connect(self.set_mic)
        if preferred_idx is not None:
            self.mic_select.setCurrentIndex(preferred_idx)
        self.mic_sel_Layout.addWidget(self.mic_select)

        self.main_layout.addLayout(self.mic_sel_Layout)

        self.continuous_recording = QCheckBox("Continuous Recording")
        if settings.audio.continuous_recording:
            self.continuous_recording.setCheckState(Qt.CheckState.Checked)
        self.continuous_recording.checkStateChanged.connect(self.set_continuous_recording)
        self.main_layout.addWidget(self.continuous_recording)

        self.buttonHlayout = QHBoxLayout()

        self.rec_screen_button = QPushButton("Screenshot")
        self.rec_screen_button.released.connect(ut.recordHotKeyScreenshot)
        self.buttonHlayout.addWidget(self.rec_screen_button)

        self.rec_audio_button = QPushButton("Audio")
        self.rec_audio_button.released.connect(self.getAudio)
        self.buttonHlayout.addWidget(self.rec_audio_button)

        self.rec_both_button = QPushButton("Both")
        self.rec_both_button.released.connect(self.getBoth)
        self.buttonHlayout.addWidget(self.rec_both_button)

        self.main_layout.addLayout(self.buttonHlayout)

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

        self.main_layout.addLayout(self.playerHlayout)

        self.listwidget = QListWidget()
        # self.listwidget.addItems(["test 1", "test 2", "test 3"])
        self.listwidget.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.listwidget.setAlternatingRowColors(True)
        self.listwidget.itemSelectionChanged.connect(self.changedSelection)

        self.monitoring_button = QPushButton("Start Monitoring")
        self.monitoring_button.released.connect(self.audioMonitor)
        self.main_layout.addWidget(self.monitoring_button)

        self.main_layout.addWidget(self.listwidget)

        self.main_layout.addWidget(QLabel("Last Anki Note"))

        self.last_note_info = QLabel("Word:\nSentence:")
        self.main_layout.addWidget(self.last_note_info)

        widget = QWidget()
        widget.setLayout(self.main_layout)
        self.setCentralWidget(widget)

        ut.signals.confirm.connect(self.openConfirmationDialog)

        self.threadpool = QThreadPool()
        self.player = Player_Worker()
        # self.player.setAutoDelete(False)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.updateSlider)
        self.timer.start(500)

        start_monitoring_anki(self.update_anki_note_info)

        # self.settings_window = SettingsWindow()
        # self.settings_window.show()

    def update_anki_note_info(self, info):
        self.last_note_info.setText(info)

    def add_session(self):
        new_session_name = str(datetime.now())
        sessionsdb.sessions_dict[new_session_name] = {
            "AppName": "",
            "WindowTitle": "",
        }
        self.session_select.clear()
        self.session_select.addItems(list(sessionsdb.sessions_dict.keys()))
        self.session_select.setCurrentIndex(list.index(list(sessionsdb.sessions_dict.keys()), new_session_name))

    def updateSlider(self):
        # if self.player._data is None:
        #     return
        # print(f"timeout value: {int(self.player.cursor/self.player.frames*10000)}, cursor: {self.player.cursor}, frames: {self.player.frames}")
        value = 0
        if PlayerState.cursor > 0:
            value = int(PlayerState.cursor/PlayerState.total_intervals*10000)
        self.audio_slider.setValue(value)

    def refresh_app_list(self):
        self.apps = getAllApps()
        self.app_select.clear()
        self.app_select.addItems([a.localizedName() for a in self.apps])

    def set_session(self, key):
        if not key:
            return
        print(f"session: {sessionsdb.sessions_dict[key]}")
        settings.general.last_session = key
        self.app_select.currentIndexChanged.disconnect(self.set_app)
        self.window_select.currentIndexChanged.disconnect(self.set_window)
        self.window_select.setCurrentIndex(-1)
        try:
            self.apps = getAllApps()
            self.app_select.clear()
            self.app_select.addItems([a.localizedName() for a in self.apps])
            self.app_select.setCurrentIndex(-1)
            for i in range(len(self.apps)):
                if self.apps[i].localizedName() == sessionsdb.sessions_dict[key]["AppName"]:
                    self.app_select.setCurrentIndex(i)
                    break
            if self.app_select.currentIndex() < 0:
                raise Exception(f"{sessionsdb.sessions_dict[key]["AppName"]} not running")
            self.set_app(self.app_select.currentIndex())
            self.window_select.setCurrentIndex(-1)
            for i in range(len(self.windows)):
                if self.windows[i]["kCGWindowName"] == sessionsdb.sessions_dict[key]["WindowTitle"]:
                    self.window_select.setCurrentIndex(i)
                    break
            if self.window_select.currentIndex() < 0:
                raise Exception(f"{sessionsdb.sessions_dict[key]["WindowTitle"]} window not found")
            self.set_window(self.window_select.currentIndex())
        except Exception as e:
            print(e)
        finally:
            self.app_select.currentIndexChanged.connect(self.set_app)
            self.window_select.currentIndexChanged.connect(self.set_window)

    def set_app(self, index):
        if index < 0:
            return
        print(f"self.apps[index]: {self.apps[index]}")
        sessionsdb.sessions_dict[settings.general.last_session]["AppName"] = self.apps[index].localizedName()
        # ut.app = self.apps[index]
        # ut.proc = getAS_Process(ut.se, ut.app)
        self.windows = getAppWindows(self.apps[index])
        self.window_select.clear()
        self.window_select.addItems([w["kCGWindowName"] for w in self.windows])

    def set_window(self, index):

        try:
            print(f"self.windows[index]: {self.windows[index]}")
            screenshot.win = self.windows[index]
            sessionsdb.sessions_dict[settings.general.last_session]["WindowTitle"] = self.windows[index]["kCGWindowName"]
            # ut.selected_win_AX = getAXWindowFromWindowInfo(getAppAXWindows(ut.app), self.windows[index])
        except Exception as e:
            print(e)
            screenshot.win = None

    def set_mic(self, index):
        audio.mic = self.mikes[index]
        settings.update_option("audio", "mic", self.mikes[index].name)
        if audio.buffer is None or audio.buffer.channels != audio.mic.channels:
            audio.buffer = audio.AudioBuffer(channels=audio.mic.channels, is_primary=True)
            audio.secondary_buffer = audio.AudioBuffer(channels=audio.mic.channels, max_time=0.5)

    def set_continuous_recording(self, state):
        print(f"state: {state}")
        if state:
            settings.audio.continuous_recording = True
        else:
            settings.audio.continuous_recording = False

    def audioMonitor(self):
        if not self.av_monitoring:
            self.monitoring_button.setText("Stop Monitoring")
            self.av_monitoring = True
        else:
            self.monitoring_button.setText("Start Monitoring")
            self.av_monitoring = False

        if audio.record_audio_buffer is None:
            audio.record_audio_buffer = audio.recordAudioBuffer()
            audio.record_audio_buffer.start()
        else:
            audio.record_audio_buffer.stop_recording()
            audio.record_audio_buffer.join()
            audio.record_audio_buffer = None

        if screenshot.screenshot_manager is None:
            screenshot.screenshot_manager = screenshot.ScreenshotManager(interval=settings.image.capture_interval)
            screenshot.screenshot_manager.start()
        else:
            screenshot.screenshot_manager.stop_recording()
            screenshot.screenshot_manager.join()
            screenshot.screenshot_manager = None

    def getAudio(self):
        if self.av_monitoring:
            sel_indeces = sorted([x.row() for x in self.listwidget.selectedIndexes()])
            # print(self.audio_data)
            # print(sel_indeces)
            ut.recordHotKeyAudio(data=[self.audio_data[i] for i in sel_indeces])
        else:
            ut.recordHotKeyAudio()

    def getBoth(self):
        if self.av_monitoring:
            sel_indeces = sorted([x.row() for x in self.listwidget.selectedIndexes()])
            ut.recordHotKeyBoth(data=[self.audio_data[i] for i in sel_indeces])
        else:
            ut.recordHotKeyBoth()

    def openConfirmationDialog(self, data):
        confirmD = ConfirmationDialog(data)
        if confirmD.exec():
            ut.confirmed = True
        else:
            ut.confirmed = False
        ut.condition.set()

    def playAudio(self):
        # if self.player._data is None:
        #     sel_indeces = sorted([x.row() for x in self.listwidget.selectedIndexes()])
        #     self.player._data = np.concatenate([self.audio_data[i] for i in sel_indeces])
        #     self.player.frames = self.player._data.shape[0]
        #     self.player._dataT = self.player._data.T
        if PlayerState.playing:
            self.play_button.setText("Play")
            PlayerState.playing = False
            # audio.PLAYBACK = False
        else:
            self.play_button.setText("Pause")
            PlayerState.total_intervals = len(audio.buffer)
            # PlayerState.cursor = 0
            PlayerState.playing = True
            self.player = Player_Worker()
            # audio.PLAYBACK = True
            self.threadpool.start(self.player)

    def slider_moved(self):
        # if self.player._data is None:
        #     return
        PlayerState.playing = False
        PlayerState.cursor = int((self.audio_slider.value()/10000)*PlayerState.total_intervals)

    def changedSelection(self):
        self.player._data = None
        self.player.frames = None
        self.player._dataT = None
        self.player.cursor = 0
        self.player.playing = False
        audio.PLAYBACK = False


def update_all_dbs():
    settings.store_settings()
    imagedb.store_imgs(screenshot.images_tmp)
    audiodb.store_buffer(audio.buffer)
    linedb.store_lines(util.sockets.text_stored)
    sessionsdb.store_sessions()


def main():
    createAggregateDevice()
    # ut.hotkeys.start()
    # ut.hotkeys.wait()
    util.sockets.ws_server = util.sockets.WebsocketManagerThread(ws_port=settings.general.ws_port, listen_urls=settings.general.listen_urls)
    util.sockets.ws_server.start()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    if sys.platform == "darwin":
        window.raise_()
    app.exec()
    # ut.hotkeys.stop()
    destroyAggregateDevice()

    if audio.record_audio_buffer:
        audio.record_audio_buffer.stop_recording()
        audio.record_audio_buffer.join()
        audio.record_audio_buffer = None

    if screenshot.screenshot_manager:
        screenshot.screenshot_manager.stop_recording()
        screenshot.screenshot_manager.join()
        screenshot.screenshot_manager = None

    util.sockets.ws_server.stop_server()

    update_all_dbs()


if __name__ == "__main__":
    main()
