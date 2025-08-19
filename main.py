import sys

from PySide6.QtCore import Qt
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
    QAbstractItemView
)

import util
from AggregateDevice import createAggregateDevice, destroyAggregateDevice


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.apps = util.getAllApps()
        self.windows = None
        self.mikes, loop_idx = util.get_mics()

        self.audio_data = []
        self.audio_info = []

        self.setWindowTitle("My App")
        self.layout = QVBoxLayout()

        self.session_select = QComboBox()
        self.session_select.addItems(list(util.sessions.keys()))
        self.session_select.currentTextChanged.connect(self.set_session)
        self.layout.addWidget(self.session_select)

        self.app_select = QComboBox()
        self.app_select.addItems([a.localizedName() for a in self.apps])
        self.app_select.currentIndexChanged.connect(self.set_app)
        self.layout.addWidget(self.app_select)

        self.window_select = QComboBox()
        self.window_select.currentIndexChanged.connect(self.set_window)
        self.layout.addWidget(self.window_select)

        self.mic_select = QComboBox()
        self.mic_select.addItems([f"{mic}" for mic in self.mikes])
        self.mic_select.currentIndexChanged.connect(self.set_mic)
        if loop_idx is not None:
            self.mic_select.setCurrentIndex(loop_idx)
        self.layout.addWidget(self.mic_select)

        self.use_audio_button = QCheckBox("Use audio button")
        self.use_audio_button.stateChanged.connect(self.set_use_audio_button)
        # self.use_audio_button.checkStateChanged.connect(self.set_use_audio_button)
        self.layout.addWidget(self.use_audio_button)

        self.buttonHlayout = QHBoxLayout()

        self.rec_screen_button = QPushButton("Screenshot")
        self.rec_screen_button.released.connect(util.recordHotKeyScreenshot)
        self.buttonHlayout.addWidget(self.rec_screen_button)

        self.rec_audio_button = QPushButton("Audio")
        self.rec_audio_button.released.connect(util.recordHotKeyAudio)
        self.buttonHlayout.addWidget(self.rec_audio_button)

        self.rec_both_button = QPushButton("Both")
        self.rec_both_button.released.connect(util.recordHotKeyBoth)
        self.buttonHlayout.addWidget(self.rec_both_button)

        self.layout.addLayout(self.buttonHlayout)

        self.listwidget = QListWidget()
        self.listwidget.addItems(["test 1", "test 2", "test 3"])
        self.listwidget.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)

        self.monitoring_button = QPushButton("Start Monitoring Audio")
        self.monitoring_button.released.connect(lambda: util.startMonitoring(self.listwidget, self.audio_data, self.audio_info))
        self.layout.addWidget(self.monitoring_button)

        self.layout.addWidget(self.listwidget)

        self.set_session(self.session_select.currentText())

        widget = QWidget()
        widget.setLayout(self.layout)
        self.setCentralWidget(widget)

    def set_session(self, key):
        print(f"session: {util.sessions[key]}")
        self.app_select.currentIndexChanged.disconnect(self.set_app)
        self.window_select.currentIndexChanged.disconnect(self.set_window)
        try:
            self.apps = util.getAllApps()
            for i in range(len(self.apps)):
                if self.apps[i].localizedName() == util.sessions[key]["AppName"]:
                    self.app_select.setCurrentIndex(i)
                    break
            self.set_app(self.app_select.currentIndex())
            for i in range(len(self.windows)):
                if self.windows[i]["kCGWindowName"] == util.sessions[key]["WindowTitle"]:
                    self.window_select.setCurrentIndex(i)
                    break
            self.set_window(self.window_select.currentIndex())
        except Exception as e:
            print(e)
        finally:
            self.app_select.currentIndexChanged.connect(self.set_app)
            self.window_select.currentIndexChanged.connect(self.set_window)

    def set_app(self, index):
        print(f"self.apps[index]: {self.apps[index]}")
        util.app = self.apps[index]
        util.proc = util.getAS_Process(util.se, util.app)
        self.windows = util.getAppWindows(self.apps[index])
        self.window_select.clear()
        self.window_select.addItems([w["kCGWindowName"] for w in self.windows])

    def set_window(self, index):
        try:
            print(f"self.windows[index]: {self.windows[index]}")
            util.selected_win_AX = util.getAXWindowFromWindowInfo(util.getAppAXWindows(util.app), self.windows[index])
        except Exception as e:
            print(e)

    def set_mic(self, index):
        util.mic = self.mikes[index]

    def set_use_audio_button(self, state):
        print(f"state: {state}")
        if state:
            util.use_button = True
        else:
            util.use_button = True


createAggregateDevice()
util.hotkeys.start()
util.hotkeys.wait()
app = QApplication(sys.argv)
window = MainWindow()
window.show()
app.exec()
util.hotkeys.stop()
destroyAggregateDevice()
