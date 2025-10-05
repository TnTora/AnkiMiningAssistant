from datetime import timedelta
from PySide6.QtCore import (
    QSize,
    Qt,
)
from PySide6.QtWidgets import (
    QBoxLayout,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLineEdit,
    QStackedWidget,
    QToolButton,
    QWidget,
    QCheckBox,
    QComboBox,
    QLabel,
    QListWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QSlider,
    QSizePolicy,
    QSpinBox,
    QDoubleSpinBox,
    QStackedLayout,
    QTabWidget
)

from util.database import settings, get_attributes


class GeneralPage(QWidget):

    def __init__(self):
        super().__init__()

        self.buffer_label = QLabel("Buffer Length")
        self.buffer_label.setStyleSheet("""
            font-size:13pt;
        """)

        self.buffer_info = QLabel("Amount of time to store audio, images and lines")
        self.buffer_info.setWordWrap(True)
        self.buffer_info.setStyleSheet("""
            font-size:9pt;
            font-weight:bold;
        """)

        self.buffer_spin = QSpinBox()
        self.buffer_spin.setMaximum(1800)
        self.buffer_spin.setSuffix("s")
        self.buffer_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.ws_port_label = QLabel("WebSocket Port")
        self.ws_port_label.setStyleSheet("""
            font-size:13pt;
        """)

        self.ws_port_spin = QSpinBox()
        self.ws_port_spin.setMaximum(65535)
        self.ws_port_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.ws_port_info = QLabel("PORT used to communicate with texthooker")
        self.ws_port_info.setWordWrap(True)
        self.ws_port_info.setStyleSheet("""
            font-size:9pt;
            font-weight:bold;
        """)

        self.listen_urls_label = QLabel("Listen To WebSockets")
        self.listen_urls_label.setStyleSheet("""
            font-size:13pt;
        """)

        self.listen_urls_info = QLabel("URLs to listen to in order to receive text")
        self.listen_urls_info.setWordWrap(True)
        self.listen_urls_info.setStyleSheet("""
            font-size:9pt;
            font-weight:bold;
        """)

        self.listen_urls = {}

        for url in settings.general.listen_urls:
            tmp_line_edit = QLineEdit(url)
            tmp_tool_button = QToolButton()

            tmp_tool_button.setText("-")
            tmp_tool_button.setMinimumSize(QSize(23, 22))
            tmp_tool_button.clicked.connect(lambda: self.remove_listen_url(url))

            self.listen_urls[url] = [tmp_line_edit, tmp_tool_button]

        self.new_url_edit = QLineEdit()
        self.add_url_button = QToolButton()
        self.add_url_button.setText("+")
        self.add_url_button.setMinimumSize(QSize(23, 22))
        self.add_url_button.clicked.connect(self.add_listen_url)

        """
        Building Layout
        """

        self.buffer_layout = QVBoxLayout()
        self.buffer_layout.addWidget(self.buffer_label)
        self.buffer_layout.addWidget(self.buffer_info)

        self.ws_port_layout = QVBoxLayout()
        self.ws_port_layout.addWidget(self.ws_port_label)
        self.ws_port_layout.addWidget(self.ws_port_info)

        self.listen_urls_layout = QVBoxLayout()
        self.listen_urls_layout.addWidget(self.listen_urls_label, alignment=Qt.AlignTop)
        self.listen_urls_layout.addWidget(self.listen_urls_info, alignment=Qt.AlignTop)
        self.listen_urls_layout.setStretch(1, 1)

        self.urls_form = QFormLayout()
        self.urls_form.setContentsMargins(0, 0, 9, 0)
        self.urls_form.setVerticalSpacing(10)
        self.urls_form.setLabelAlignment(Qt.AlignRight)
        self.urls_form.setFormAlignment(Qt.AlignRight)
        for url in self.listen_urls:
            self.urls_form.addRow(self.listen_urls[url][0], self.listen_urls[url][1])
        self.urls_form.addRow(self.new_url_edit, self.add_url_button)

        self.main_layout = QGridLayout()
        self.main_layout.setVerticalSpacing(30)
        self.main_layout.addLayout(self.buffer_layout, 0, 0)
        self.main_layout.addWidget(self.buffer_spin, 0, 1, alignment=Qt.AlignRight)
        self.main_layout.addLayout(self.ws_port_layout, 1, 0)
        self.main_layout.addWidget(self.ws_port_spin, 1, 1, alignment=Qt.AlignRight)
        self.main_layout.addLayout(self.listen_urls_layout, 2, 0)
        self.main_layout.addLayout(self.urls_form, 2, 1)

        self.setLayout(self.main_layout)

    def add_listen_url(self):
        new_url = self.new_url_edit.text()
        new_line_edit = QLineEdit(new_url)
        new_button = QToolButton()
        new_button.setText("-")
        new_button.setMinimumSize(QSize(23, 22))
        new_button.clicked.connect(lambda: self.remove_listen_url(new_url))
        self.urls_form.takeRow(self.add_url_button)
        self.listen_urls[new_url] = [new_line_edit, new_button]
        self.urls_form.addRow(new_line_edit, new_button)
        self.new_url_edit.setText("")
        self.urls_form.addRow(self.new_url_edit, self.add_url_button)

    def remove_listen_url(self, url):
        row = self.listen_urls.pop(url)
        self.urls_form.removeRow(row[1])


class SettingsWindow(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Settings")
        self.setMinimumWidth(660)
        self.setMinimumHeight(390)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # self.setWindowFlags(Qt.WindowType.FramelessWindowHint)

        self.sidebar = QGroupBox()
        self.sidebar.setStyleSheet("""
            QPushButton {
                background-color:rgb(57, 57, 57);
                border: 0px;
                min-width: 115px;
                min-height: 60px;
            }

            QPushButton:hover {
                background-color:rgb(91, 91, 91);
            }
        """)
        self.sidebar.setMinimumWidth(115)
        self.sidebar.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)

        self.sidebar_label = QLabel("Settings")
        self.sidebar_label.setAlignment(Qt.AlignCenter)
        self.sidebar_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.sidebar_label.setStyleSheet("""
            QLabel {
                font-size:18pt;
            }
        """)

        self.sidebar_spacer = QWidget()
        self.sidebar_spacer.setMinimumHeight(20)

        self.general_button = QPushButton("General")
        self.general_button.setCheckable(True)

        self.anki_button = QPushButton("Anki")
        self.anki_button.setCheckable(True)

        self.audio_button = QPushButton("Audio")
        self.audio_button.setCheckable(True)

        self.image_button = QPushButton("Image")
        self.image_button.setCheckable(True)

        self.stacked_widget = QStackedWidget()

        self.general_page = GeneralPage()
        self.stacked_widget.addWidget(self.general_page)

        self.apply_button = QPushButton("Apply")
        self.cancel_button = QPushButton("Cancel")
        self.ok_button = QPushButton("OK")

        """
        Building Layout
        """

        self.sidebar_layout = QVBoxLayout()
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_layout.setSpacing(0)
        self.sidebar_layout.addWidget(self.sidebar_label)
        self.sidebar_layout.addWidget(self.sidebar_spacer)
        self.sidebar_layout.addWidget(self.general_button)
        self.sidebar_layout.addWidget(self.anki_button)
        self.sidebar_layout.addWidget(self.audio_button)
        self.sidebar_layout.addWidget(self.image_button)

        self.group_layout = QVBoxLayout()
        self.group_layout.setContentsMargins(0, 12, 0, 12)
        self.group_layout.setSpacing(0)
        self.group_layout.setAlignment(Qt.AlignTop)
        self.group_layout.addLayout(self.sidebar_layout)
        self.sidebar.setLayout(self.group_layout)

        self.confirmation_box_layout = QHBoxLayout()
        self.confirmation_box_layout.setAlignment(Qt.AlignRight)
        self.confirmation_box_layout.setSpacing(13)
        self.confirmation_box_layout.setContentsMargins(0, 10, 12, 12)
        self.confirmation_box_layout.addWidget(self.apply_button)
        self.confirmation_box_layout.addWidget(self.cancel_button)
        self.confirmation_box_layout.addWidget(self.ok_button)

        self.settings_layout = QVBoxLayout()
        self.settings_layout.addWidget(self.stacked_widget)
        self.settings_layout.addLayout(self.confirmation_box_layout)

        self.window_layout = QHBoxLayout()
        self.window_layout.setContentsMargins(0, 0, 0, 0)
        self.window_layout.setSpacing(0)
        self.window_layout.addWidget(self.sidebar)
        self.window_layout.addLayout(self.settings_layout)

        # self.central_widget = QWidget()
        # self.central_widget.setLayout(self.window_layout)
        self.setLayout(self.window_layout)


