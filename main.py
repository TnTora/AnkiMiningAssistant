import sys
from datetime import datetime

from PySide6.QtGui import (
    QFont,
    QIcon,
    # QPalette,
)
from PySide6.QtCore import (
    QCoreApplication,
    QItemSelectionModel,
    QSize,
    Qt,
    # QThreadPool,
    # Slot,
    QTimer,
    Slot,
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
from util.AggregateDevice import createAggregateDevice, destroyAggregateDevice
from util.database import (
    settings,
    imagedb,
    audiodb,
    linedb,
    sessionsdb
)

from util.mac import (
    getAllApps,
    getAppWindows,
)
import util.sockets
from util import audio
from util import screenshot

from settings_gui import SettingsWindow

from confirmation_dialog import NotePreviewDialog, AlertDialog, SelectLineDialog

from player import PlayerState, Player_Worker


class SelectionError(Exception):
    """Raised when automatic selection in a widget fails."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class MainWindow(QMainWindow):
    def __init__(self):  # noqa: PLR0915
        super().__init__()
        self.settings_window = None
        self.lines_shown = False
        self.with_lines_height = None
        self.apps = getAllApps()
        self.windows = None
        self.mikes, preferred_idx = audio.get_mics()
        self.player_state = PlayerState()

        self.audio_data = []
        self.audio_info = []
        self.av_monitoring = False

        self.setWindowTitle("AnkiMiningAssistant")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()

        # self.setStyleSheet(f"""
        #     QToolButton {{
        #         border: 1px solid #555555;
        #         border-radius: 6px;
        #         background-color: {self.palette().color(QPalette.ColorRole.Base).name()};
        #     }}

        #     QToolButton:pressed {{
        #         background-color: {self.palette().color(QPalette.ColorRole.Light).name()};
        #     }}
        # """)

        """
        Creating Widgets
        """

        self.session_box = QGroupBox("Session")
        self.session_box.setFixedWidth(280)
        self.session_box.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.anki_box = QGroupBox("Anki")
        self.anki_box.setMinimumWidth(370)
        self.anki_box.setMaximumHeight(180)

        self.session_select = QComboBox()
        self.session_select.setEditable(True)
        self.session_select.addItems(list(sessionsdb.sessions_dict.keys()))
        self.session_select.currentIndexChanged.connect(self.set_session)

        self.session_name_timer = QTimer(self)
        self.session_name_timer.setInterval(2000)
        self.session_name_timer.timeout.connect(self.update_session_name)

        self.session_select.editTextChanged.connect(
            lambda: self.session_name_timer.start()
        )

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
        self.app_select.setCurrentIndex(-1)
        self.app_select.activated.connect(self.set_app)

        self.win_sel_label = QLabel("Window: ")

        self.window_select = QComboBox()
        self.window_select.activated.connect(self.set_window)

        self.apps_windows_timer = QTimer(self)
        self.apps_windows_timer.setInterval(1000)
        self.apps_windows_timer.timeout.connect(self.update_apps_windows)
        self.apps_windows_timer.start()

        self.mic_sel_label = QLabel("Mic: ")

        self.mic_select = QComboBox()
        self.mic_select.addItems([mic.name for mic in self.mikes])
        self.mic_select.currentIndexChanged.connect(self.set_mic)
        if preferred_idx is not None:
            self.mic_select.setCurrentIndex(preferred_idx)

        self.continuous_recording = QCheckBox("Continuous Recording")

        if settings.audio.continuous_recording:
            self.continuous_recording.setCheckState(Qt.CheckState.Checked)

        self.continuous_recording.checkStateChanged.connect(
            lambda state: self.set_check_setting(state, "continuous_recording")
        )

        # self.rec_screen_button = QPushButton("Screenshot")
        self.rec_screen_button = QToolButton()
        self.rec_screen_button.setIcon(QIcon("picture-1.png"))
        self.rec_screen_button.setIconSize(QSize(25, 25))
        self.rec_screen_button.setMinimumWidth(40)
        self.rec_screen_button.setMinimumHeight(40)
        self.rec_screen_button.released.connect(
            lambda: self.update_note_button(update_img=True, update_audio=False)
        )

        # self.rec_audio_button = QPushButton("Audio")
        self.rec_audio_button = QToolButton()
        self.rec_audio_button.setIcon(QIcon("voice-recording-1.png"))
        self.rec_audio_button.setIconSize(QSize(25, 25))
        self.rec_audio_button.setMinimumWidth(40)
        self.rec_audio_button.setMinimumHeight(40)
        self.rec_audio_button.released.connect(
            lambda: self.update_note_button(update_img=False, update_audio=True)
        )

        self.rec_both_button = QToolButton()
        self.rec_both_button.setIcon(QIcon("audio-pic-1.png"))
        self.rec_both_button.setIconSize(QSize(30, 30))
        self.rec_both_button.setMinimumWidth(40)
        self.rec_both_button.setMinimumHeight(40)
        self.rec_both_button.released.connect(
            lambda: self.update_note_button(update_img=True, update_audio=True)
        )

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

        self.auto_update_check.checkStateChanged.connect(
            lambda state: self.set_check_setting(state, "auto_update")
        )
        self.open_in_browser_check = QCheckBox("Open in Browser")

        self.open_in_browser_check.checkStateChanged.connect(
            lambda state: self.set_check_setting(state, "open_in_browser")
        )

        self.preview_note_check = QCheckBox("Preview Note")

        self.preview_note_check.checkStateChanged.connect(
            lambda state: self.set_check_setting(state, "preview_note")
        )

        self.audio_slider = QSlider()
        self.audio_slider.setMinimum(0)
        self.audio_slider.setMaximum(10000)
        self.audio_slider.setValue(0)
        self.audio_slider.setSingleStep(1)
        self.audio_slider.setOrientation(Qt.Horizontal)
        self.audio_slider.sliderPressed.connect(self.slider_pressed)
        self.audio_slider.sliderReleased.connect(self.slider_released)

        self.play_button = QPushButton("Play")
        self.play_button.released.connect(self.playAudio)

        self.show_lines_label = QLabel("∨ Hide Lines")  # noqa: RUF001
        self.show_lines_label.mouseReleaseEvent = self.toggle_lines
        self.settings_button = QPushButton("Settings")
        self.settings_button.released.connect(self.open_config)

        self.listwidget = QListWidget()
        self.list_font = QFont()
        self.list_font.setPointSize(20)
        self.listwidget.setFont(self.list_font)
        self.listwidget.setSpacing(10)
        self.listwidget.setWordWrap(True)
        self.listwidget.setMinimumHeight(1)
        # self.listwidget.addItems(["日本人が肉を日常食べるようになったのは明治以降である." for _ in range(20)])
        self.listwidget.addItems([line.text for line in util.sockets.text_stored])
        self.listwidget.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        # self.listwidget.itemSelectionChanged.connect(self.changedSelection)
        self.listwidget.itemSelectionChanged.connect(self.update_selected_lines)

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
        self.session_combo_layout.addWidget(self.del_session_button)
        self.session_combo_layout.addWidget(self.new_session_button)
        self.session_combo_layout.setStretch(0, 1)

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
        self.button_layout.setContentsMargins(0, 5, 10, 0)
        self.button_layout.addWidget(self.rec_screen_button)
        self.button_layout.addWidget(self.rec_audio_button)
        self.button_layout.addWidget(self.rec_both_button)

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
        self.middle_row.addWidget(self.show_lines_label, alignment=Qt.AlignLeft | Qt.AlignBottom)
        self.middle_row.addWidget(self.settings_button, alignment=Qt.AlignRight)

        # self.bottom_half = QVBoxLayout()
        # self.bottom_half.setSpacing(0)
        # self.bottom_half.setContentsMargins(0, 0, 0, 0)
        # self.bottom_half.addLayout(self.middle_row)
        # self.bottom_half.addWidget(self.listwidget)

        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(0, 10, 0, 0)
        self.main_layout.setSpacing(0)
        self.main_layout.setAlignment(Qt.AlignTop)
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
                color: #cccccc;
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
        for url in settings.general.listen_urls:
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

        self.status_bar.addPermanentWidget(self.anki_status)
        self.status_bar.addPermanentWidget(self.ws_status)

        # self.status_bar.addPermanentWidget(QLabel("Listeners: "))
        for listener in self.listeners_status.values():
            self.status_bar.addPermanentWidget(listener)

        widget = QWidget()
        widget.setLayout(self.main_layout)
        self.setCentralWidget(widget)

        """
        Extra setup
        """

        # Set session after creating othr widgets since they are
        # used in set_session
        if settings.general.last_session in sessionsdb.sessions_dict:
            tmp_idx = list.index(list(sessionsdb.sessions_dict.keys()), settings.general.last_session)
            self.session_select.setCurrentIndex(tmp_idx)
        else:
            tmp_idx = list.index(list(sessionsdb.sessions_dict.keys()), "Manual")
            self.session_select.setCurrentIndex(tmp_idx)
        self.set_session(tmp_idx)

        util.sockets.socket_signals.ws_state.connect(self.update_ws_status)
        util.sockets.socket_signals.listener_state.connect(self.update_listener_status)
        util.sockets.socket_signals.line_received.connect(self.update_listwidget)

        anki.anki_signals.anki_status.connect(self.update_anki_status)
        anki.anki_signals.last_note_changed.connect(self.update_anki_note_info)
        anki.anki_signals.note_update_info.connect(self.openAlertDialog)
        anki.anki_signals.note_update_select_line.connect(self.openLineSelectionDialog)
        anki.anki_signals.note_update_confirm.connect(self.openConfirmDialog)

        # self.threadpool = QThreadPool()
        self.player = None
        self.player_state.signals.cursor_update.connect(self.updateSlider)

        # Start the main websocket server and handle the connections that will listen for new lines
        util.sockets.ws_server = util.sockets.WebsocketManagerThread(ws_port=settings.general.ws_port, listen_urls=settings.general.listen_urls)
        util.sockets.ws_server.start()

        anki.start_monitoring_anki()

        # foo = NotePreviewDialog(
        #     imgs=screenshot.images_tmp.deque,
        #     audio_data=audio.buffer,
        #     audio_range=(10, 200),
        #     sentence="日本人が肉を日常食べるようになったのは明治以降である. 日本人が肉を日常食べるようになったのは明治以降である."
        # )
        # foo.open()

    def open_config(self) -> None:
        self.settings_window = SettingsWindow()
        self.settings_window.show()

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
        # self.listwidget.clear()
        # self.listwidget.addItems([line.text for line in util.sockets.text_stored])
        self.listwidget.addItems(line.text)
        # self.listwidget.setCurrentRow(-1)

    @Slot(str, str)
    def update_anki_note_info(self, expression: str, sentence: str) -> None:
        # self.last_note_info.setText(info)
        self.anki_last_card.setText(expression)
        self.anki_sentence.setText(sentence)

    def update_note_button(self, *, update_img: bool, update_audio: bool) -> None:
        if settings.general.last_session == "Manual":
            # print("manual")
            anki.start_manual_note_update(update_img=update_img, update_audio=update_audio)
            return
        anki.start_auto_note_update(update_img=update_img, update_audio=update_audio, confirmation=sessionsdb.current_session["preview_note"])

    def update_session_name(self) -> None:
        new_name = self.session_select.currentText()

        if not new_name:
            return
        if new_name == settings.general.last_session:
            return

        sessionsdb.sessions_dict[new_name] = sessionsdb.sessions_dict.pop(settings.general.last_session)
        settings.general.last_session = new_name
        # print(f"settings.general.last_session: {settings.general.last_session}")
        self.session_name_timer.stop()

    def update_selected_lines(self):
        tmp_idx = sorted([a.row() for a in self.listwidget.selectedIndexes()])
        tmp_idx = tuple(tmp_idx)
        util.sockets.selected_idxs = tmp_idx

    def update_apps_windows(self):
        """Update apps and windows selection QComboBox."""
        if self.app_select.view().isVisible() or self.window_select.view().isVisible():
            return

        if self.app_select.currentIndex() < 0:
            self.apps = getAllApps()
            self.app_select.clear()
            self.app_select.addItems([a.localizedName() for a in self.apps])
            self.app_select.setCurrentIndex(-1)
        else:
            curr_text_app = self.app_select.currentText()
            old_apps = self.apps
            self.apps = getAllApps()
            self.app_select.clear()
            app_names = [a.localizedName() for a in self.apps]
            self.app_select.addItems(app_names)

            if curr_text_app not in app_names:
                self.app_select.setCurrentIndex(-1)
                self.window_select.clear()
                return

            self.app_select.setCurrentText(curr_text_app)

            # Check if this app windows are found to avoid removing windows
            # when changing Space if finding windows in all spaces is not possible
            # windows_check = getAppWindows(QCoreApplication.applicationPid(), brute_force=False)
            # print(f"windows_check: {windows_check}")

            # print(f"idx: {self.window_select.currentIndex()}", *self.windows, sep="\n")

            curr_text_window = self.window_select.currentText()
            # found_private = self.windows[self.window_select.currentIndex()].found_private if curr_text_window != "**No Window Selected**" else True

            # if not (windows_check or found_private):
            #     return

            self.windows = getAppWindows(self.apps[self.app_select.currentIndex()])
            self.window_select.clear()
            win_titles = [w.title for w in self.windows]
            self.window_select.addItems(win_titles)
            self.window_select.addItem("**No Window Selected**")
            if curr_text_window not in [*win_titles, "**No Window Selected**"]:
                self.window_select.setCurrentText("**No Window Selected**")
                self.set_window(None)
                return
            self.window_select.setCurrentText(curr_text_window)

    def add_session(self) -> None:
        new_session_name = str(datetime.now())
        sessionsdb.sessions_dict[new_session_name] = {
            "AppName": "",
            "WindowTitle": "",
            "continuous_recording": settings.audio.continuous_recording,
            "auto_update": settings.anki.auto_update_last_note,
            "open_in_browser": settings.anki.open_note_in_gui,
            "preview_note": False
        }
        self.session_select.clear()
        self.session_select.addItems(list(sessionsdb.sessions_dict.keys()))
        self.session_select.setCurrentIndex(list.index(list(sessionsdb.sessions_dict.keys()), new_session_name))

    def del_session(self) -> None:
        sessionsdb.sessions_dict.pop(self.session_select.currentText())
        self.session_select.clear()
        self.session_select.addItems(list(sessionsdb.sessions_dict.keys()))

    def updateSlider(self) -> None:
        value = 0
        if self.player_state.total_intervals > 0:
            value = int(self.player_state.cursor/self.player_state.total_intervals*10000)
        self.audio_slider.setValue(value)

    def refresh_app_list(self) -> None:
        self.apps = getAllApps()
        self.app_select.clear()
        self.app_select.addItems([a.localizedName() for a in self.apps])

    def set_session(self, idx) -> None:
        settings.general.last_session = list(sessionsdb.sessions_dict.keys())[idx]
        sessionsdb.current_session = sessionsdb.sessions_dict[settings.general.last_session]

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

        self.window_select.setCurrentIndex(-1)
        try:
            self.apps = getAllApps()
            self.app_select.clear()
            self.app_select.addItems([a.localizedName() for a in self.apps])
            self.app_select.setCurrentIndex(-1)

            for i in range(len(self.apps)):
                if self.apps[i].localizedName() == sessionsdb.current_session["AppName"]:
                    self.app_select.setCurrentIndex(i)
                    break

            if self.app_select.currentIndex() < 0:
                if sessionsdb.current_session["AppName"]:
                    msg = f"'{sessionsdb.current_session["AppName"]}' not running"
                else:
                    msg = ""
                self.status_bar.showMessage(msg, 5000)
                raise SelectionError(msg)  # noqa: TRY301

            self.set_app(self.app_select.currentIndex())
            self.window_select.setCurrentIndex(-1)

            for i in range(len(self.windows)):
                if self.windows[i].title == sessionsdb.current_session["WindowTitle"]:
                    self.window_select.setCurrentIndex(i)
                    break

            if self.window_select.currentIndex() < 0:
                msg = f"'{sessionsdb.current_session["WindowTitle"]}' window not found"
                self.status_bar.showMessage(msg, 5000)
                self.window_select.setCurrentText("**No Window Selected**")
                self.set_window(None)
                raise SelectionError(msg)  # noqa: TRY301

            self.set_window(self.window_select.currentIndex())
        except SelectionError as e:
            print(e)

    def set_app(self, index: int) -> None:
        if index < 0:
            return

        sessionsdb.sessions_dict[settings.general.last_session]["AppName"] = self.apps[index].localizedName()
        self.windows = getAppWindows(self.apps[index])
        self.window_select.clear()
        self.window_select.addItems([w.title for w in self.windows])
        self.window_select.addItem("**No Window Selected**")
        self.window_select.setCurrentText("**No Window Selected**")
        self.set_window(None)

    def set_window(self, index: int) -> None:
        try:
            screenshot.win = self.windows[index]
            sessionsdb.sessions_dict[settings.general.last_session]["WindowTitle"] = self.windows[index].title
        except (KeyError, IndexError, TypeError) as e:
            # import traceback
            # traceback.print_exc()
            print(e)
            screenshot.win = None

    def set_mic(self, index: int) -> None:
        audio.mic = self.mikes[index]
        settings.update_option("audio", "mic", self.mikes[index].name)
        if audio.buffer is None or audio.buffer.channels != audio.mic.channels:
            audio.buffer = audio.AudioBuffer(channels=audio.mic.channels, is_primary=True)
            audio.secondary_buffer = audio.AudioBuffer(channels=audio.mic.channels, max_time=0.5)
            self.player_state.total_intervals = len(audio.buffer)

    def set_check_setting(self, state: Qt.CheckState, setting: str) -> None:
        if state == Qt.CheckState.Checked:
            sessionsdb.sessions_dict[settings.general.last_session][setting] = True
        else:
            sessionsdb.sessions_dict[settings.general.last_session][setting] = False

    def audioMonitor(self) -> None:
        if not self.av_monitoring:
            self.monitoring_button.setText("Stop Monitoring")
            self.av_monitoring = True
            self.play_button.setDisabled(True)
        else:
            self.monitoring_button.setText("Start Monitoring")
            self.av_monitoring = False
            self.play_button.setDisabled(False)

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
        confirm_dialog = NotePreviewDialog(imgs, audio_data, audio_interval, sentence)
        res = confirm_dialog.exec()
        if res == QDialog.DialogCode.Accepted:
            anki.anki_signals.returned_value = confirm_dialog.getValues()
        else:
            anki.anki_signals.returned_value = None
        anki.anki_signals.wait_event.set()

    def playAudio(self) -> None:
        if self.player_state.playing:
            self.play_button.setText("Play")
            self.player.stop()
        else:
            self.play_button.setText("Pause")
            self.player_state.total_intervals = len(audio.buffer)
            self.player = Player_Worker(self.player_state)
            self.player.start()

    def slider_pressed(self) -> None:
        self.player_state.signals.cursor_update.disconnect(self.updateSlider)

    def slider_released(self) -> None:
        if not self.player_state.playing:
            self.player_state.cursor = int((self.audio_slider.value()/10000)*self.player_state.total_intervals)
        else:
            self.player.stop()
            self.player.join()
            # self.play_button.setText("Play")
            self.player_state.cursor = int((self.audio_slider.value()/10000)*self.player_state.total_intervals)
            self.player = Player_Worker(self.player_state)
            self.player.start()
        self.player_state.signals.cursor_update.connect(self.updateSlider)

    def changedSelection(self) -> None:
        pass

    def toggle_lines(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
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
    settings.store_settings()
    imagedb.store_imgs(screenshot.images_tmp)
    # audiodb.store_buffer(audio.buffer)
    audiodb.store_buffer_intervals(audio.buffer)
    audiodb.store_inactive_intervals(audio.buffer)
    linedb.store_lines(util.sockets.text_stored)
    sessionsdb.store_sessions()


def main() -> None:
    aggr_id, tap_id = createAggregateDevice()
    # ut.hotkeys.start()
    # ut.hotkeys.wait()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    if sys.platform == "darwin":
        window.raise_()
    app.exec()
    # ut.hotkeys.stop()
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
        window.player_state.playing = False

    util.sockets.ws_server.stop_server()

    update_all_dbs()


if __name__ == "__main__":
    main()
