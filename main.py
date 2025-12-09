import sys
from datetime import datetime
from time import sleep

from PySide6.QtGui import (
    QFont,
    QIcon,
    QPalette,
    QMouseEvent,
)
from PySide6.QtCore import (
    # QCoreApplication,
    QItemSelectionModel,
    QSize,
    Qt,
    QThreadPool,
    QRunnable,
    QTimer,
    Slot,
    QObject,
    Signal,
    QSignalBlocker,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QToolButton,
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
    QSlider,
    QSizePolicy,
    QStatusBar,
    QGroupBox,
    QGridLayout,
)

from util import anki

from util.database import (
    settings,
    imagedb,
    audiodb,
    linedb,
    sessionsdb,
)

from util.platform_util import (
    getAllApps,
    getAppWindows,
    platform,
    is_wayland,
    Window,
)

if platform == "darwin":
    from util.AggregateDevice import createAggregateDevice, destroyAggregateDevice

import util.sockets
from util import audio
from util import screenshot

from UI.settings_gui import SettingsWindow

from UI.custom_widgets.confirmation_dialog import NotePreviewDialog, AlertDialog, SelectLineDialog

if platform in ["win32", "darwin"]:
    from util.audio.player_sd import PlayerWorkerSD
    PlayerWorker = PlayerWorkerSD
else:
    from util.audio.player_sc import PlayerWorkerSC
    PlayerWorker = PlayerWorkerSC

from UI.custom_widgets import RegionSelect, CalibrationDialog

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from util.custom_typings import Session, SessionKeysBool

import logging

logger = logging.getLogger("app_logger")
logger.setLevel(logging.DEBUG)

fh = logging.FileHandler("last_run.log", mode="w")
fh.setLevel(logging.DEBUG)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
fh.setFormatter(formatter)
ch.setFormatter(formatter)

logger.addHandler(fh)
logger.addHandler(ch)


def _startMonitoring(audio_input) -> None:

    audio.record_audio_buffer = audio.recordAudioBuffer(audio_input)
    audio.record_audio_buffer.start()

    screenshot.screenshot_manager = screenshot.ScreenshotManager(interval=settings.image.capture_interval)
    screenshot.screenshot_manager.start()


def _stopMonitoring() -> None:

    if audio.record_audio_buffer is not None:
        audio.record_audio_buffer.stop_recording()
        audio.record_audio_buffer.join()
        audio.record_audio_buffer = None

    if screenshot.screenshot_manager is not None:
        screenshot.screenshot_manager.stop_recording()
        screenshot.screenshot_manager.join()
        screenshot.screenshot_manager = None


if is_wayland:
    from util.platform_util import start_screencapture, stop_screencapture, set_sources
    def startMonitoring(audio_input) -> None:
        src_type = "MONITOR" if sessionsdb.current_session["use_screen_region"] else "WINDOW"
        start_screencapture(src_type=src_type)
        _startMonitoring(audio_input)

    def stopMonitoring():
        _stopMonitoring()
        stop_screencapture()
else:
    startMonitoring = _startMonitoring
    stopMonitoring = _stopMonitoring


class UpdateSignals(QObject):
    update_apps = Signal(list, int)
    update_windows = Signal(list, int)

class UpdateWorker(QRunnable):

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.signals = UpdateSignals()
        self.stop_event = False

    def stop(self):
        self.stop_event = True

    @Slot()
    def run(self):
        try:
            while not self.stop_event:
                self.update_apps_windows()
                sleep(1)
        except RuntimeError:
            self.stop()

    def update_apps_windows(self):
        """Update apps and windows selection QComboBox."""
        if self.parent.app_select.view().isVisible() or self.parent.window_select.view().isVisible():
            return

        if sessionsdb.current_session["use_screen_region"]:
            return

        if self.parent.app_select.currentText == "**No App Selected**":
            self.parent.apps = getAllApps()
            app_names = [a.localizedName() for a in self.parent.apps]
            self.signals.update_apps.emit(app_names, -1)
        else:
            self.parent.apps = getAllApps()
            app_names = [a.localizedName() for a in self.parent.apps]

            try:
                curr_app_idx = self.parent.apps.index(self.parent.curr_app)
                self.signals.update_apps.emit(app_names, curr_app_idx)
            except ValueError:
                self.signals.update_apps.emit(app_names, -1)
                self.signals.update_windows.emit([], -1)
                return

            self.parent.windows = getAppWindows(self.parent.apps[curr_app_idx])

            win_titles = [w.title for w in self.parent.windows]

            try:
                curr_win_idx = self.parent.windows.index(self.parent.curr_win)
                self.signals.update_windows.emit(win_titles, curr_win_idx)
            except ValueError:
                self.signals.update_windows.emit(win_titles, -1)


class SessionComboBox(QComboBox):

    def __init__(self):
        super().__init__()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        new_name = self.currentText()

        if not new_name:
            return
        if new_name == settings.general.last_session:
            return

        sessionsdb.sessions_dict[new_name] = sessionsdb.sessions_dict.pop(settings.general.last_session)
        settings.general.last_session = new_name

        with QSignalBlocker(self) as blocker:
            curr_idx = self.currentIndex()
            self.clear()
            self.addItems(list(sessionsdb.sessions_dict.keys()))
            self.setCurrentIndex(curr_idx)


class ClickableLabel(QLabel):
    clicked = Signal()

    def __init__(self, text: str) -> None:
        super().__init__(text)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.clicked.emit()


class MainWindow(QMainWindow):
    def __init__(self):  # noqa: PLR0915
        super().__init__()

        # Secondary Windows
        self.settings_window = None
        self.screen_region_window = None
        self.calibration_window = None
        self.confirm_dialog = None

        # Miscellaneous Variables
        self.lines_shown = False
        self.with_lines_height = None
        self.apps = getAllApps()
        self.curr_app = None
        self.windows: list[Window] = []
        self.curr_win: Window | None = None
        self.audio_inputs, preferred_idx = audio.get_audio_inputs()
        self.audio_input = None
        self.player_state = audio.PlayerState()

        self.av_monitoring = False

        self.setWindowTitle("AnkiMiningAssistant")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()

        # --------------------------------------------------------------------------------------
        # ------------- Creating Widgets -------------------------------------------------------
        # --------------------------------------------------------------------------------------

        self.session_box = QGroupBox("Session")
        self.session_box.setFixedWidth(280)
        self.session_box.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.anki_box = QGroupBox("Anki")
        self.anki_box.setMinimumWidth(370)
        self.anki_box.setMaximumHeight(180)

        self.session_select = SessionComboBox()  #QComboBox()
        self.session_select.setEditable(True)
        self.session_select.addItems(list(sessionsdb.sessions_dict.keys()))
        self.session_select.currentIndexChanged.connect(self.set_session)
        # self.session_select.focusOutEvent = self.update_session_name

        self.del_session_button = QPushButton("-")
        self.del_session_button.setMinimumWidth(21)
        self.del_session_button.setMaximumWidth(21)
        self.del_session_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.del_session_button.released.connect(self.del_session)

        self.new_session_button = QPushButton("+")
        self.new_session_button.setMinimumWidth(21)
        self.new_session_button.setMaximumWidth(21)
        self.new_session_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.new_session_button.released.connect(self.add_session)

        self.app_sel_label = QLabel("App: ")
        self.app_sel_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

        self.app_select = QComboBox()
        self.app_select.addItems([a.localizedName() for a in self.apps])
        self.app_select.addItem("**No App Selected**")
        self.app_select.setCurrentIndex(-1)
        self.app_select.activated.connect(self.set_app)

        self.win_sel_label = QLabel("Window: ")

        self.window_select = QComboBox()
        self.window_select.addItem("**No Window Selected**")
        self.window_select.activated.connect(self.set_window)

        if is_wayland:
            self.select_source_button = QPushButton("Select Source")
            self.select_source_button.clicked.connect(set_sources)

        self.audio_input_sel_label = QLabel("Audio Input: ")

        self.audio_input_select = QComboBox()
        self.audio_input_select.addItems([audio_input.name for audio_input in self.audio_inputs])
        self.audio_input_select.addItem("**No Input Selected**")
        self.audio_input_select.currentIndexChanged.connect(self.set_audio_input)

        self.screen_region_check = QCheckBox("Use screen region: ")
        self.screen_region_check.checkStateChanged.connect(
            self.toggle_screen_region
        )

        self.screen_region_button = QPushButton("Set")
        self.screen_region_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.screen_region_button.clicked.connect(self.open_screen_region)

        self.continuous_recording = QCheckBox("Continuous Recording")

        if settings.audio.continuous_recording:
            self.continuous_recording.setCheckState(Qt.CheckState.Checked)

        self.continuous_recording.checkStateChanged.connect(
            self.set_check_setting_slot_gen("continuous_recording")
        )

        # Screenshot Button
        self.rec_screen_button = QToolButton()
        self.rec_screen_button.setIcon(QIcon("assets/screenshot_button.png"))
        self.rec_screen_button.setIconSize(QSize(25, 25))
        self.rec_screen_button.setMinimumWidth(40)
        self.rec_screen_button.setMinimumHeight(40)
        self.rec_screen_button.released.connect(
            self.update_note_button_slot_gen(update_img=True, update_audio=False)
        )

        # Audio Button
        self.rec_audio_button = QToolButton()
        self.rec_audio_button.setIcon(QIcon("assets/audio_button.png"))
        self.rec_audio_button.setIconSize(QSize(25, 25))
        self.rec_audio_button.setMinimumWidth(40)
        self.rec_audio_button.setMinimumHeight(40)
        self.rec_audio_button.released.connect(
            self.update_note_button_slot_gen(update_img=False, update_audio=True)
        )

        # Screenshot/Audio Button
        self.rec_both_button = QToolButton()
        self.rec_both_button.setIcon(QIcon("assets/screenshot_audio_button.png"))
        self.rec_both_button.setIconSize(QSize(30, 30))
        self.rec_both_button.setMinimumWidth(40)
        self.rec_both_button.setMinimumHeight(40)
        self.rec_both_button.released.connect(
            self.update_note_button_slot_gen(update_img=True, update_audio=True)
        )

        self.anki_font = QFont()
        self.anki_font.setPointSize(18)
        self.anki_last_card = QLabel()
        self.anki_last_card.setFont(self.anki_font)
        self.sentence_font = QFont()
        self.sentence_font.setPointSize(15)
        self.anki_sentence = QLabel()
        self.anki_sentence.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.anki_sentence.setWordWrap(True)
        self.anki_sentence.setFont(self.sentence_font)

        self.auto_update_check = QCheckBox("Auto Update")

        self.auto_update_check.checkStateChanged.connect(
            self.set_check_setting_slot_gen("auto_update")
        )
        self.open_in_browser_check = QCheckBox("Open in Browser")

        self.open_in_browser_check.checkStateChanged.connect(
            self.set_check_setting_slot_gen("open_in_browser")
        )

        self.preview_note_check = QCheckBox("Preview Note")

        self.preview_note_check.checkStateChanged.connect(
            self.set_check_setting_slot_gen("preview_note")
        )

        self.audio_slider = QSlider()
        self.audio_slider.setMinimum(0)
        self.audio_slider.setMaximum(10000)
        self.audio_slider.setValue(0)
        self.audio_slider.setSingleStep(1)
        self.audio_slider.setOrientation(Qt.Orientation.Horizontal)
        self.audio_slider.sliderPressed.connect(self.slider_pressed)
        self.audio_slider.sliderReleased.connect(self.slider_released)

        self.play_button = QPushButton("Play")
        self.play_button.released.connect(self.playAudio)

        self.show_lines_label = ClickableLabel("∨ Hide Lines")  # noqa: RUF001
        self.show_lines_label.clicked.connect(self.toggle_lines)
        self.settings_button = QPushButton("Settings")
        self.settings_button.released.connect(self.open_config)

        self.listwidget = QListWidget()
        self.list_font = QFont()
        self.list_font.setPointSize(20)
        self.listwidget.setFont(self.list_font)
        self.listwidget.setSpacing(10)
        self.listwidget.setWordWrap(True)
        self.listwidget.setMinimumHeight(1)
        # self.listwidget.setAlternatingRowColors(True)
        # self.listwidget.addItems(["日本人が肉を日常食べるようになったのは明治以降である." for _ in range(20)])
        self.listwidget.addItems([line.text for line in util.sockets.text_stored])
        self.listwidget.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.listwidget.itemSelectionChanged.connect(self.update_selected_lines)

        if not self.lines_shown:
            self.show_lines_label.setText("> Show Lines")
            self.listwidget.hide()

        self.monitoring_button = QPushButton("Start Monitoring")
        self.monitoring_button.released.connect(self.toggleMonitoring)
        self.monitoring_button.setEnabled(False)

        # --------------------------------------------------------------------------------------
        # ------------- Building Layout --------------------------------------------------------
        # --------------------------------------------------------------------------------------

        self.session_box_layout = QVBoxLayout()
        self.session_box_layout.setSpacing(5)

        self.session_combo_layout = QHBoxLayout()
        self.session_combo_layout.addWidget(self.session_select)
        self.session_combo_layout.addWidget(self.del_session_button)
        self.session_combo_layout.addWidget(self.new_session_button)
        self.session_combo_layout.setStretch(0, 1)

        self.screen_region_hbox = QHBoxLayout()
        self.screen_region_hbox.setContentsMargins(0, 10, 0, 5)
        self.screen_region_hbox.addWidget(self.screen_region_check)
        self.screen_region_hbox.addWidget(self.screen_region_button)

        self.session_box_layout.addLayout(self.session_combo_layout)

        if is_wayland:
            self.session_box_layout.addWidget(self.select_source_button)
        else:
            self.session_box_layout.addWidget(self.app_sel_label)
            self.session_box_layout.addWidget(self.app_select)
            self.session_box_layout.addWidget(self.win_sel_label)
            self.session_box_layout.addWidget(self.window_select)

        self.session_box_layout.addWidget(self.audio_input_sel_label)
        self.session_box_layout.addWidget(self.audio_input_select)
        self.session_box_layout.addLayout(self.screen_region_hbox)
        self.session_box_layout.addWidget(self.continuous_recording)
        self.session_box.setLayout(self.session_box_layout)

        self.session_out_layout = QVBoxLayout()
        # self.session_out_layout.setContentsMargins(0, 0, 10, 0)
        self.session_out_layout.addWidget(self.session_box)

        self.button_layout = QVBoxLayout()
        self.button_layout.setContentsMargins(0, 20, 10, 0)
        self.button_layout.addWidget(self.rec_screen_button)
        self.button_layout.addWidget(self.rec_audio_button)
        self.button_layout.addWidget(self.rec_both_button)

        self.anki_info_grid = QGridLayout()
        self.anki_info_grid.setColumnStretch(1, 1)
        self.anki_info_grid.setRowStretch(1, 1)

        self.anki_info_grid.addWidget(QLabel("Expression:"), 0, 0, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.anki_info_grid.addWidget(QLabel("Sentence:"), 1, 0, alignment=Qt.AlignmentFlag.AlignTop)
        self.anki_info_grid.addWidget(self.anki_last_card, 0, 1)
        self.anki_info_grid.addWidget(self.anki_sentence, 1, 1)

        self.anki_checks_layout = QHBoxLayout()
        self.anki_checks_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.anki_checks_layout.addWidget(self.auto_update_check)
        self.anki_checks_layout.addWidget(self.open_in_browser_check)
        self.anki_checks_layout.addWidget(self.preview_note_check)

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
        self.middle_row.addWidget(self.show_lines_label, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        self.middle_row.addWidget(self.settings_button, alignment=Qt.AlignmentFlag.AlignRight)

        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(0, 10, 0, 0)
        self.main_layout.setSpacing(0)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.main_layout.addLayout(self.top_row)
        # self.main_layout.addLayout(self.bottom_half)
        self.main_layout.addLayout(self.middle_row)
        self.main_layout.addWidget(self.listwidget)

        status_margin = 10 if "mac" in QApplication.style().name() else 0

        status_style = f"""
            QCheckBox::indicator:!enabled{{
                background-color: #e50000;
                border: 1px solid #e50000;
                border-radius: 5px;
                width: 9px;
                height: 9px;
                margin-right:{status_margin}px;
            }}
            QCheckBox::indicator:checked:!enabled{{
                background-color: #27b700;
                border: 1px solid #27b700;
            }}
            QCheckBox::indicator:indeterminate:!enabled{{
                background-color: #e28204;
                border: 1px solid #e28204;
            }}
            QCheckBox:!enabled{{
                color: {self.palette().color(QPalette.ColorRole.Text).name()};
            }}
        """

        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet(status_style)
        self.setStatusBar(self.status_bar)

        self.anki_status = QCheckBox("Anki: ")
        self.anki_status.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.anki_status.setTristate(True)
        self.anki_status.setEnabled(False)
        self.anki_status.setCheckState(Qt.CheckState.Unchecked)
        # self.anki_status.setStyleSheet(status_style)

        self.ws_status = QCheckBox("WS: ")
        self.ws_status.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.ws_status.setTristate(True)
        self.ws_status.setEnabled(False)
        self.ws_status.setCheckState(Qt.CheckState.Unchecked)
        # self.ws_status.setStyleSheet(status_style)

        self.listeners_status = {}

        self.status_bar.addPermanentWidget(self.anki_status)
        self.status_bar.addPermanentWidget(self.ws_status)

        self.add_listeners_status()

        widget = QWidget()
        widget.setLayout(self.main_layout)
        self.setCentralWidget(widget)

        # --------------------------------------------------------------------------------------
        # ------------- Extra setup ------------------------------------------------------------
        # --------------------------------------------------------------------------------------

        # Set session after creating othr widgets since they are
        # used in set_session
        if settings.general.last_session in sessionsdb.sessions_dict:
            tmp_idx = list(sessionsdb.sessions_dict.keys()).index(settings.general.last_session)
            self.session_select.setCurrentIndex(tmp_idx)
        else:
            tmp_idx = list(sessionsdb.sessions_dict.keys()).index("Manual")
            self.session_select.setCurrentIndex(tmp_idx)
        self.set_session(tmp_idx)

        # set audio_input after creating monitoring button
        if preferred_idx is not None:
            self.audio_input_select.setCurrentIndex(preferred_idx)
            self.set_audio_input(preferred_idx)
        else:
            self.audio_input_select.setCurrentText("**No Input Selected**")

        util.sockets.socket_signals.ws_state.connect(self.update_ws_status)
        util.sockets.socket_signals.listener_state.connect(self.update_listener_status)
        util.sockets.socket_signals.line_received.connect(self.update_listwidget)

        anki.anki_signals.anki_status.connect(self.update_anki_status)
        anki.anki_signals.last_note_changed.connect(self.update_anki_note_info)
        anki.anki_signals.note_update_info.connect(self.openAlertDialog)
        anki.anki_signals.note_update_select_line.connect(self.openLineSelectionDialog)
        anki.anki_signals.note_update_confirm.connect(self.openConfirmDialog)

        self.player = PlayerWorker(self.player_state)
        self.player_state.signals.cursor_update.connect(self.updateSlider)
        self.player_state.signals.playing_state_changed.connect(
            self.update_play_button
        )

        if not is_wayland:
            # Start thread to monitor apps/windows
            self.threadpool = QThreadPool()
            self.update_worker = UpdateWorker(self)
            self.threadpool.start(self.update_worker)
            self.update_worker.signals.update_apps.connect(self.update_apps_combo)
            self.update_worker.signals.update_windows.connect(self.update_windows_combo)

        # Start the main websocket server and handle the connections that will listen for new lines
        util.sockets.ws_server = util.sockets.WebsocketManagerThread(ws_port=settings.general.ws_port, listen_urls=settings.general.listen_urls)
        util.sockets.ws_server.start()

        anki.start_monitoring_anki()

    def add_listeners_status(self):
        for url in settings.general.listen_urls:
            if url in self.listeners_status:
                continue
            if not self.listeners_status:
                tmp_status = QCheckBox("Listening: ")
            else:
                tmp_status = QCheckBox()
            tmp_status.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            tmp_status.setTristate(True)
            tmp_status.setEnabled(False)
            tmp_status.setToolTip(url)
            tmp_status.setCheckState(Qt.CheckState.Unchecked)

            self.listeners_status[url] = tmp_status
            self.status_bar.addPermanentWidget(tmp_status)

    def update_listeners(self):
        if util.sockets.ws_server is not None:
            util.sockets.ws_server.stop_server()
            util.sockets.ws_server.join()
        util.sockets.ws_server = util.sockets.WebsocketManagerThread(ws_port=settings.general.ws_port, listen_urls=settings.general.listen_urls)

        self.add_listeners_status()

        util.sockets.ws_server.start()

    def open_config(self) -> None:
        if self.settings_window is not None:
            self.settings_window = None
        self.settings_window = SettingsWindow()
        self.settings_window.general_page.listeners_updated.connect(
            self.update_listeners
        )
        self.settings_window.show()

    def open_screen_region(self) -> None:

        def handle_cancel():
            if sessionsdb.current_session["screen_region"] == (0, 0, 0, 0):
                self.screen_region_check.setChecked(False)

        if is_wayland and settings.image.pixel_ratio is None:
            self.calibration_window = CalibrationDialog()
            self.calibration_window.show()
        else:
            x1, y1, x2, y2 = sessionsdb.current_session["screen_region"]
            self.screen_region_window = RegionSelect(x1, y1, x2-x1, y2-y1)
            self.screen_region_window.cancelled.connect(handle_cancel)
            self.screen_region_window.show()

    @Slot(str, int)
    def update_listener_status(self, url: str, state: int) -> None:
        if url == "all":
            for listener in self.listeners_status.values():
                listener.setCheckState(Qt.CheckState(state))
            return
        self.listeners_status[url].setCheckState(Qt.CheckState(state))

    @Slot(int)
    def update_ws_status(self, state: int) -> None:
        self.ws_status.setCheckState(Qt.CheckState(state))

    @Slot(int)
    def update_anki_status(self, state: int) -> None:
        self.anki_status.setCheckState(Qt.CheckState(state))

    @Slot(object)
    def update_listwidget(self, line) -> None:
        self.listwidget.addItem(line.text)

    @Slot(str, str)
    def update_anki_note_info(self, expression: str, sentence: str) -> None:
        # self.last_note_info.setText(info)
        self.anki_last_card.setText(expression)
        self.anki_sentence.setText(sentence)

    @Slot(bool)
    def update_play_button(self, state):
        text = "Pause" if state else "Play"
        self.play_button.setText(text)

    def update_note_button_slot_gen(self, *, update_img: bool, update_audio: bool) -> None:
        @Slot()
        def update_note_button() -> None:
            if settings.general.last_session == "Manual":
                anki.start_manual_note_update(update_img=update_img, update_audio=update_audio)
                return
            anki.start_auto_note_update(update_img=update_img, update_audio=update_audio, confirmation=sessionsdb.current_session["preview_note"])
        return update_note_button

    def update_selected_lines(self):
        tmp_idx = sorted([a.row() for a in self.listwidget.selectedIndexes()])
        tmp_idx = tuple(tmp_idx)
        util.sockets.selected_idxs = tmp_idx

    @Slot(list, int)
    def update_apps_combo(self, app_names, app_idx):
        """Update app selection QComboBox."""
        self.app_select.clear()
        self.app_select.addItems(app_names)
        self.app_select.addItem("**No App Selected**")
        if app_idx > -1:
            self.app_select.setCurrentIndex(app_idx)
        else:
            self.app_select.setCurrentText("**No App Selected**")
            if self.curr_app is None:
                return
            self.set_app(None)


    @Slot(list, int)
    def update_windows_combo(self, win_titles, win_idx):
        """Update window selection QComboBox."""
        self.window_select.clear()
        self.window_select.addItems(win_titles)
        self.window_select.addItem("**No Window Selected**")
        if win_idx > -1:
            self.window_select.setCurrentIndex(win_idx)
        else:
            self.window_select.setCurrentText("**No Window Selected**")
            if self.curr_win is None:
                return
            self.set_window(None)

    def add_session(self) -> None:
        new_session_name = str(datetime.now())
        sessionsdb.sessions_dict[new_session_name]: Session = {
            "AppName": "",
            "WindowTitle": "",
            "continuous_recording": settings.audio.continuous_recording,
            "auto_update": settings.anki.auto_update_last_note,
            "open_in_browser": settings.anki.open_note_in_gui,
            "preview_note": True,
            "use_screen_region": False,
            "screen_region": (0, 0, 0, 0),
        }
        self.session_select.clear()
        self.session_select.addItems(list(sessionsdb.sessions_dict.keys()))
        self.session_select.setCurrentIndex(list(sessionsdb.sessions_dict.keys()).index(new_session_name))

    def del_session(self) -> None:
        sessionsdb.sessions_dict.pop(self.session_select.currentText())
        self.session_select.clear()
        self.session_select.addItems(list(sessionsdb.sessions_dict.keys()))

    def updateSlider(self) -> None:
        value = 0
        if self.player_state.total_intervals > 0:
            value = int(self.player_state.cursor/self.player_state.total_intervals*10000)
        self.audio_slider.setValue(value)

    def set_session(self, idx) -> None:
        if self.av_monitoring:
            logger.info("Session change detected, pausing monitoring")
            self.toggleMonitoring()

        settings.general.last_session = list(sessionsdb.sessions_dict.keys())[idx]
        sessionsdb.current_session = sessionsdb.sessions_dict[settings.general.last_session]
        self.curr_app = None
        self.curr_win = None

        self.continuous_recording.setChecked(sessionsdb.current_session["continuous_recording"])
        self.auto_update_check.setChecked(sessionsdb.current_session["auto_update"])
        self.open_in_browser_check.setChecked(sessionsdb.current_session["open_in_browser"])
        self.preview_note_check.setChecked(sessionsdb.current_session["preview_note"])

        if settings.general.last_session == "Manual":
            self.auto_update_check.setEnabled(False)
            self.preview_note_check.setEnabled(False)
            self.session_select.setEditable(False)
        else:
            self.auto_update_check.setEnabled(True)
            self.preview_note_check.setEnabled(True)
            self.session_select.setEditable(True)

        try:
            self.apps = getAllApps()
            self.app_select.clear()
            self.app_select.addItems([a.localizedName() for a in self.apps])
            self.app_select.addItem("**No App Selected**")
            self.app_select.setCurrentText("**No App Selected**")

            for i in range(len(self.apps)):
                if self.apps[i].localizedName() == sessionsdb.current_session["AppName"]:
                    self.app_select.setCurrentIndex(i)
                    break

            if self.app_select.currentText() == "**No App Selected**":
                if sessionsdb.current_session["AppName"]:
                    msg = f"'{sessionsdb.current_session["AppName"]}' not running"
                    self.status_bar.showMessage(msg, 5000)
                    logger.info(msg)
                return

            self.set_app(self.app_select.currentIndex())
            self.window_select.setCurrentText("**No Window Selected**")

            for i in range(len(self.windows)):
                if self.windows[i].title == sessionsdb.current_session["WindowTitle"]:
                    self.window_select.setCurrentIndex(i)
                    break

            if self.window_select.currentText() == "**No Window Selected**":
                msg = f"'{sessionsdb.current_session["WindowTitle"]}' window not found"
                self.status_bar.showMessage(msg, 5000)
                # self.window_select.setCurrentText("**No Window Selected**")
                # self.set_window(None)
                logger.info(msg)
                return

            self.set_window(self.window_select.currentIndex())
        finally:
            self.screen_region_check.setChecked(sessionsdb.current_session["use_screen_region"])

    def set_app(self, index: int | None) -> None:
        if index is None or index < 0:
            self.curr_app = None
            logger.info("No App Selected")
            return

        sessionsdb.current_session["AppName"] = self.apps[index].localizedName()
        self.curr_app = self.apps[index]

        self.windows = getAppWindows(self.apps[index])
        self.window_select.clear()
        self.window_select.addItems([w.title for w in self.windows])
        self.window_select.addItem("**No Window Selected**")
        self.window_select.setCurrentText("**No Window Selected**")
        self.set_window(None)


    def set_window(self, index: int | None) -> None:
        if index is None or index < 0:
            screenshot.win = None
            self.curr_win = None
            logger.info("No Window Selected")
            return

        screenshot.win = self.windows[index]
        sessionsdb.current_session["WindowTitle"] = self.windows[index].title
        self.curr_win = self.windows[index]


    def set_audio_input(self, index: int) -> None:
        if index < 0:
            return

        if self.audio_input_select.currentText() == "**No Input Selected**":
            self.monitoring_button.setEnabled(False)
            # audio.audio_input = None
            return

        prev_channels = audio.buffers["primary"].channels if "primary" in audio.buffers else audio.AudioBuffer.get_db_channels()

        if prev_channels and self.audio_inputs[index].channels != prev_channels:
            alert = AlertDialog(
                f"Current AudioBuffer using {prev_channels} channels while "
                f"selected input uses {self.audio_inputs[index].channels}.\n\n"
                "If you procede, the current buffer will be emptied.\n",
                cancel=True,
            )
            if not alert.exec():
                try:
                    old_idx = self.audio_inputs.index(self.audio_input)
                    self.audio_input_select.setCurrentIndex(old_idx)
                except ValueError:
                    self.audio_input_select.setCurrentText("**No Input Selected**")
                return
            audiodb.clear()
            if "primary" in audio.buffers:
                audio.buffers["primary"].deque.clear()

        self.audio_input = self.audio_inputs[index]
        settings.update_option("audio", "audio_input", self.audio_inputs[index].name)
        if "primary" not in audio.buffers:
            # audio.buffer = audio.AudioBuffer(channels=audio.audio_input.channels, is_primary=True)
            # audio.secondary_buffer = audio.AudioBuffer(channels=audio.audio_input.channels, max_time=0.5)
            audio.buffers["primary"] = audio.AudioBuffer(channels=self.audio_input.channels, is_primary=True)
            audio.buffers["secondary"] = audio.AudioBuffer(channels=self.audio_input.channels, max_time=0.5)
            self.player_state.total_intervals = len(audio.buffers["primary"])

        self.monitoring_button.setEnabled(True)

    def set_check_setting_slot_gen(self, setting: "SessionKeysBool") -> None:
        @Slot(Qt.CheckState)
        def set_check_setting(state: Qt.CheckState) -> None:
            if state == Qt.CheckState.Checked:
                sessionsdb.current_session[setting] = True
            else:
                sessionsdb.current_session[setting] = False
        return set_check_setting

    def toggle_screen_region(self, state: Qt.CheckState) -> None:
        if state == Qt.CheckState.Checked:
            sessionsdb.current_session["use_screen_region"] = True
            self.app_select.setEnabled(False)
            self.window_select.setEnabled(False)
            self.set_window(None)
            if sessionsdb.current_session["screen_region"] == (0, 0, 0, 0):
                self.open_screen_region()
        else:
            sessionsdb.current_session["use_screen_region"] = False
            self.app_select.setEnabled(True)
            self.window_select.setEnabled(True)
            self.set_window(self.window_select.currentIndex())

    def toggleMonitoring(self) -> None:
        if not self.av_monitoring:
            self.monitoring_button.setText("Stop Monitoring")
            self.av_monitoring = True
            self.play_button.setDisabled(True)
            self.audio_input_select.setDisabled(True)
            self.screen_region_check.setDisabled(True)
            self.screen_region_button.setDisabled(True)
            startMonitoring(audio_input=self.audio_input)
        else:
            stopMonitoring()
            self.monitoring_button.setText("Start Monitoring")
            self.av_monitoring = False
            self.play_button.setDisabled(False)
            self.audio_input_select.setDisabled(False)
            self.screen_region_check.setDisabled(False)
            self.screen_region_button.setDisabled(False)

    @Slot(str)
    def openAlertDialog(self, txt: str) -> None:
        alert = AlertDialog(txt)
        alert.exec()

    @Slot(list)
    def openLineSelectionDialog(self, lines: list) -> None:
        select_dialog = SelectLineDialog(lines)
        res = select_dialog.exec()
        if res == QDialog.DialogCode.Accepted:
            anki.anki_signals.returned_value = select_dialog.selected_line()
        else:
            anki.anki_signals.returned_value = None
        anki.anki_signals.wait_event.set()

    @Slot(list, object, tuple, str)
    def openConfirmDialog(self, imgs: list, audio_data, audio_interval: tuple, sentence: str) -> None:
        self.confirm_dialog = NotePreviewDialog(imgs, audio_data, audio_interval, sentence)
        res = self.confirm_dialog.exec()
        if res == QDialog.DialogCode.Accepted:
            anki.anki_signals.returned_value = self.confirm_dialog.getValues()
        else:
            anki.anki_signals.returned_value = None
        anki.anki_signals.wait_event.set()
        self.confirm_dialog = None

    def playAudio(self) -> None:
        if "primary" not in audio.buffers:
            return
        if self.player_state.playing:
            self.player.stop()
        else:
            self.player_state.total_intervals = len(audio.buffers["primary"])
            self.player = PlayerWorker(self.player_state)
            self.player.start()

    def slider_pressed(self) -> None:
        self.player_state.signals.cursor_update.disconnect(self.updateSlider)

    def slider_released(self) -> None:
        if not self.player_state.playing:
            self.player_state.cursor = int((self.audio_slider.value()/10000)*self.player_state.total_intervals)
        else:
            self.player.stop()
            self.player.join()
            self.player_state.cursor = int((self.audio_slider.value()/10000)*self.player_state.total_intervals)
            self.player = PlayerWorker(self.player_state)
            self.player.start()
        self.player_state.signals.cursor_update.connect(self.updateSlider)

    @Slot()
    def toggle_lines(self) -> None:
        if not self.lines_shown:
            self.lines_shown = True
            self.listwidget.show()
            self.show_lines_label.setText("∨ Hide Lines")  # noqa: RUF001
            height = self.with_lines_height or self.minimumSizeHint().height() + 200
            self.resize(self.width(), height)
        else:
            self.listwidget.setCurrentRow(-1)
            for row in (a.row() for a in self.listwidget.selectedIndexes()):
                self.listwidget.setCurrentRow(row, QItemSelectionModel.SelectionFlag.Deselect)
            self.lines_shown = False
            self.with_lines_height = self.height()
            self.listwidget.hide()
            self.show_lines_label.setText("> Show Lines")
            self.resize(self.width(), self.minimumSizeHint().height())


def update_all_dbs() -> None:
    # TODO: update some dbs while the app is running
    # TODO: create window to show user saving progress
    logger.info("Updating database...")
    logger.info("Saving settings...")
    settings.store_settings()
    logger.info("Saving images...")
    imagedb.store_imgs(screenshot.images_tmp)
    logger.info("Saving audio...")
    if "primary" in audio.buffers:
        audiodb.store_buffer_intervals(audio.buffers["primary"])
        audiodb.store_inactive_intervals(audio.buffers["primary"])
    logger.info("Saving lines")
    linedb.store_lines(util.sockets.text_stored)
    logger.info("Saving sessions")
    sessionsdb.store_sessions()


def main() -> None:
    aggr_id, tap_id = None, None

    if platform == "darwin":
        aggr_id, tap_id = createAggregateDevice(private=True)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()

    if sys.platform == "darwin":
        window.raise_()

    app.exec()
    if not is_wayland:
        window.update_worker.stop()

    if aggr_id is not None:
        destroyAggregateDevice(aggr_id, tap_id)

    if audio.record_audio_buffer:
        audio.record_audio_buffer.stop_recording()
        audio.record_audio_buffer.join()
        audio.record_audio_buffer = None

    if screenshot.screenshot_manager:
        screenshot.screenshot_manager.stop_recording()
        screenshot.screenshot_manager.join()
        screenshot.screenshot_manager = None

    if window.player_state.playing:
        window.player.stop()

    if util.sockets.ws_server:
        util.sockets.ws_server.stop_server()

    update_all_dbs()


if __name__ == "__main__":
    main()
