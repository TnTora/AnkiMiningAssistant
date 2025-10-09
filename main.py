import sys
import soundcard as sc
# import numpy as np
from datetime import datetime

from PySide6.QtGui import QFont
from PySide6.QtCore import (
    Qt,
    QRunnable,
    QThreadPool,
    # Slot,
    QTimer,
)
from PySide6.QtWidgets import (
    QApplication,
    QToolButton,
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
    QStatusBar,
    QGroupBox,
    QGridLayout,
)

from util.AggregateDevice import createAggregateDevice, destroyAggregateDevice
from util.database import (
    settings,
    imagedb,
    audiodb,
    linedb,
    sessionsdb
)
from util.anki import start_monitoring_anki
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

from settings_gui import SettingsWindow


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

    def run(self):

        if PlayerState.cursor == PlayerState.total_intervals:
            PlayerState.cursor = 0

        with sc.default_speaker().player(samplerate=settings.audio.samplerate, blocksize=83) as sp:
            for interval in audio.buffer.slice_(start_idx=PlayerState.cursor):
                if not PlayerState.playing:
                    PlayerState.playing = False
                    break
                sp.play(interval.data)
                PlayerState.cursor += 1


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings_window = None
        self.lines_shown = False
        self.with_lines_height = None
        self.apps = getAllApps()
        self.windows = None
        self.mikes, preferred_idx = audio.get_mics()

        self.audio_data = []
        self.audio_info = []
        self.av_monitoring = False

        self.setWindowTitle("AnkiMiningAssistant")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()

        """
        Creating Widgets
        """

        self.session_box = QGroupBox("Session")
        self.session_box.setMaximumWidth(280)
        self.session_box.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.anki_box = QGroupBox("Anki")
        self.anki_box.setMinimumWidth(370)
        self.anki_box.setMaximumHeight(180)

        self.session_select = QComboBox()
        self.session_select.setEditable(True)
        self.session_select.addItems(list(sessionsdb.sessions_dict.keys()))
        self.session_select.currentTextChanged.connect(self.set_session)

        self.new_session_button = QPushButton("+")
        self.new_session_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.new_session_button.released.connect(self.add_session)

        self.app_sel_label = QLabel("App: ")
        self.app_sel_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

        self.app_select = QComboBox()
        self.app_select.addItems([a.localizedName() for a in self.apps])
        self.app_select.setCurrentIndex(-1)
        self.app_select.currentIndexChanged.connect(self.set_app)

        self.win_sel_label = QLabel("Window: ")

        self.window_select = QComboBox()
        self.window_select.currentIndexChanged.connect(self.set_window)

        # Set session after creating app and window widgets since they are
        # used in set_session
        if settings.general.last_session:
            self.session_select.setCurrentIndex(list.index(list(sessionsdb.sessions_dict.keys()), settings.general.last_session))

        self.mic_sel_label = QLabel("Mic: ")

        self.mic_select = QComboBox()
        self.mic_select.addItems([mic.name for mic in self.mikes])
        self.mic_select.currentIndexChanged.connect(self.set_mic)
        if preferred_idx is not None:
            self.mic_select.setCurrentIndex(preferred_idx)

        self.continuous_recording = QCheckBox("Continuous Recording")

        if settings.audio.continuous_recording:
            self.continuous_recording.setCheckState(Qt.CheckState.Checked)

        self.continuous_recording.checkStateChanged.connect(self.set_continuous_recording)

        # self.rec_screen_button = QPushButton("Screenshot")
        self.rec_screen_button = QToolButton()
        self.rec_screen_button.setMinimumWidth(50)
        self.rec_screen_button.setMinimumHeight(50)
        self.rec_screen_button.released.connect(ut.recordHotKeyScreenshot)

        # self.rec_audio_button = QPushButton("Audio")
        self.rec_audio_button = QToolButton()
        self.rec_audio_button.setMinimumWidth(50)
        self.rec_audio_button.setMinimumHeight(50)
        self.rec_audio_button.released.connect(self.getAudio)

        self.anki_font = QFont()
        self.anki_font.setPointSize(18)
        self.anki_last_card = QLabel()
        self.anki_last_card.setFont(self.anki_font)
        self.sentence_font = QFont()
        self.sentence_font.setPointSize(15)
        self.anki_sentence = QLabel()
        self.anki_sentence.setAlignment(Qt.AlignTop)
        self.anki_sentence.setWordWrap(True)
        self.anki_sentence.setFont(self.sentence_font)

        self.auto_update_check = QCheckBox("Auto Update")
        self.open_in_browser_check = QCheckBox("Open in Browser")

        self.audio_slider = QSlider()
        self.audio_slider.setMinimum(0)
        self.audio_slider.setMaximum(10000)
        self.audio_slider.setValue(0)
        self.audio_slider.setSingleStep(1)
        self.audio_slider.setOrientation(Qt.Horizontal)
        self.audio_slider.sliderReleased.connect(self.slider_released)

        self.play_button = QPushButton("Play")
        self.play_button.released.connect(self.playAudio)

        self.show_lines_label = QLabel("∨ Hide Lines")
        self.show_lines_label.mouseReleaseEvent = self.toggle_lines
        self.settings_button = QPushButton("Settings")
        self.settings_button.released.connect(self.open_config)

        self.listwidget = QListWidget()
        self.list_font = QFont()
        self.list_font.setPointSize(20)
        self.listwidget.setFont(self.list_font)
        self.listwidget.setSpacing(10)
        self.listwidget.setWordWrap(True)
        self.listwidget.addItems(["日本人が肉を日常食べるようになったのは明治以降である." for _ in range(20)])
        self.listwidget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.listwidget.itemSelectionChanged.connect(self.changedSelection)

        if not self.lines_shown:
            self.show_lines_label.setText("> Show Lines")
            self.listwidget.hide()

        self.monitoring_button = QPushButton("Start Monitoring")
        self.monitoring_button.released.connect(self.audioMonitor)

        """
        Building Layout
        """

        self.session_box_layout = QVBoxLayout()
        self.session_box_layout.setSpacing(5)

        self.session_combo_layout = QHBoxLayout()
        self.session_combo_layout.addWidget(self.session_select)
        self.session_combo_layout.addWidget(self.new_session_button)

        self.session_box_layout.addLayout(self.session_combo_layout)
        self.session_box_layout.addWidget(self.app_sel_label)
        self.session_box_layout.addWidget(self.app_select)
        self.session_box_layout.addWidget(self.win_sel_label)
        self.session_box_layout.addWidget(self.window_select)
        self.session_box_layout.addWidget(self.mic_sel_label)
        self.session_box_layout.addWidget(self.mic_select)
        self.session_box_layout.addWidget(self.continuous_recording)
        self.session_box.setLayout(self.session_box_layout)

        self.session_out_layout = QVBoxLayout()
        # self.session_out_layout.setContentsMargins(0, 0, 10, 0)
        self.session_out_layout.addWidget(self.session_box)

        self.button_layout = QVBoxLayout()
        self.button_layout.setContentsMargins(0, 0, 10, 0)
        self.button_layout.addWidget(self.rec_screen_button)
        self.button_layout.addWidget(self.rec_audio_button)
        # self.button_layout.addWidget(self.rec_both_button)

        self.anki_info_grid = QGridLayout()
        self.anki_info_grid.setColumnStretch(1, 1)
        self.anki_info_grid.setRowStretch(1, 1)

        self.anki_info_grid.addWidget(QLabel("Expression:"), 0, 0, alignment=Qt.AlignVCenter)
        self.anki_info_grid.addWidget(QLabel("Sentence:"), 1, 0, alignment=Qt.AlignTop)
        self.anki_info_grid.addWidget(self.anki_last_card, 0, 1)
        self.anki_info_grid.addWidget(self.anki_sentence, 1, 1)

        self.anki_checks_layout = QHBoxLayout()
        self.anki_checks_layout.setAlignment(Qt.AlignLeft)
        self.anki_checks_layout.addWidget(self.auto_update_check)
        self.anki_checks_layout.addWidget(self.open_in_browser_check)

        self.anki_box_layout = QVBoxLayout()
        self.anki_box_layout.addLayout(self.anki_info_grid)
        self.anki_box_layout.addLayout(self.anki_checks_layout)
        self.anki_box.setLayout(self.anki_box_layout)

        self.top_right_vbox = QHBoxLayout()
        # self.top_right_vbox.setContentsMargins(0, 0, 0, 10)
        self.top_right_vbox.addLayout(self.button_layout)
        self.top_right_vbox.addWidget(self.anki_box)

        self.player_h_layout = QHBoxLayout()
        self.player_h_layout.addWidget(self.monitoring_button)
        self.player_h_layout.addWidget(self.play_button)
        self.player_h_layout.addWidget(self.audio_slider)

        self.right_vbox = QVBoxLayout()
        self.right_vbox.setContentsMargins(10, 0, 0, 0)
        self.right_vbox.addLayout(self.top_right_vbox)
        self.right_vbox.addLayout(self.player_h_layout)

        self.top_row = QHBoxLayout()
        self.top_row.setContentsMargins(20, 0, 20, 0)
        self.top_row.setSpacing(5)
        self.top_row.addLayout(self.session_out_layout)
        self.top_row.addLayout(self.right_vbox)

        self.middle_row = QHBoxLayout()
        self.middle_row.setContentsMargins(10, 0, 10, 0)
        self.middle_row.addWidget(self.show_lines_label, alignment=Qt.AlignLeft | Qt.AlignBottom)
        self.middle_row.addWidget(self.settings_button, alignment=Qt.AlignRight)

        self.bottom_half = QVBoxLayout()
        self.bottom_half.setSpacing(0)
        self.bottom_half.setContentsMargins(0, 0, 0, 0)
        self.bottom_half.addLayout(self.middle_row)
        self.bottom_half.addWidget(self.listwidget)

        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(0, 10, 0, 0)
        self.main_layout.setSpacing(0)
        self.main_layout.setAlignment(Qt.AlignTop)
        self.main_layout.addLayout(self.top_row)
        self.main_layout.addLayout(self.bottom_half)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.status_bar.addPermanentWidget(QLabel("Anki: ON"))
        self.status_bar.addPermanentWidget(QLabel("WS: ON"))

        widget = QWidget()
        widget.setLayout(self.main_layout)
        self.setCentralWidget(widget)

        """
        Extra setup
        """

        ut.signals.confirm.connect(self.openConfirmationDialog)

        self.threadpool = QThreadPool()
        self.player = Player_Worker()
        # self.player.setAutoDelete(False)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.updateSlider)
        self.timer.start(500)

        start_monitoring_anki(self.update_anki_note_info)

    def open_config(self):
        # if self.settings_window is not None:
        #     self.settings_window.close()
        #     self.settings_window = None
        self.settings_window = SettingsWindow()
        self.settings_window.show()

    def update_anki_note_info(self, expression, sentence):
        # self.last_note_info.setText(info)
        self.anki_last_card.setText(expression)
        self.anki_sentence.setText(sentence)

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
            # selected_win_AX = getAXWindowFromWindowInfo(getAppAXWindows(self.apps[self.app_select.currentIndex()]), self.windows[index])
        except Exception as e:
            # import traceback
            # traceback.print_exc()
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
            pass
        else:
            ut.recordHotKeyAudio()

    def openConfirmationDialog(self, data):
        confirmD = ConfirmationDialog(data)
        if confirmD.exec():
            ut.confirmed = True
        else:
            ut.confirmed = False
        ut.condition.set()

    def playAudio(self):
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

    def slider_released(self):
        if not PlayerState.playing:
            PlayerState.cursor = int((self.audio_slider.value()/10000)*PlayerState.total_intervals)
        else:
            PlayerState.playing = False
            self.play_button.setText("Play")
            PlayerState.cursor = int((self.audio_slider.value()/10000)*PlayerState.total_intervals)
            # PlayerState.playing = True
            # self.player = Player_Worker()
            # self.threadpool.start(self.player)

    def changedSelection(self):
        self.player._data = None
        self.player.frames = None
        self.player._dataT = None
        self.player.cursor = 0
        self.player.playing = False
        audio.PLAYBACK = False

    def toggle_lines(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if not self.lines_shown:
            self.lines_shown = True
            self.listwidget.show()
            self.show_lines_label.setText("∨ Hide Lines")
            height = self.with_lines_height or self.minimumSizeHint().height() + 200
            self.resize(self.width(), height)
        else:
            self.lines_shown = False
            self.with_lines_height = self.height()
            self.listwidget.hide()
            self.show_lines_label.setText("> Show Lines")
            self.resize(self.width(), self.minimumSizeHint().height())


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
