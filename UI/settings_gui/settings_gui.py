# from datetime import timedelta
from PySide6.QtCore import (
    Qt,
    Slot,
)
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QGroupBox,
    QSpacerItem,
    QStackedWidget,
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QButtonGroup,
)

# from util.database import settings
from .general_settings import GeneralPage
from .anki_settings import AnkiPage
from .audio_settings import AudioPage
from .image_settings import ImagePage


class SettingsWindow(QWidget):

    def __init__(self):  # noqa: PLR0915
        super().__init__()

        self.setWindowTitle("Settings")
        self.setMinimumWidth(660)
        self.setMinimumHeight(390)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        # self.setWindowFlags(Qt.WindowType.FramelessWindowHint)

        self.stacked_widget = QStackedWidget()

        self.general_page = GeneralPage()
        self.stacked_widget.addWidget(self.general_page)

        self.anki_page = AnkiPage()
        self.stacked_widget.addWidget(self.anki_page)

        self.audio_page = AudioPage()
        self.stacked_widget.addWidget(self.audio_page)

        self.image_page = ImagePage()
        self.stacked_widget.addWidget(self.image_page)
        # background-color:rgb(57, 57, 57);
        self.sidebar = QGroupBox()
        # rgb(91, 91, 91)
        self.sidebar.setStyleSheet(f"""
            QPushButton {{
                border: 0px;
                min-width: 115px;
                min-height: 60px;
            }}

            QPushButton:hover {{
                background-color:{self.palette().color(QPalette.ColorRole.AlternateBase).name()};
            }}

            QPushButton:checked {{
                background-color:{self.palette().color(QPalette.ColorRole.AlternateBase).name()};
            }}
        """)

        self.sidebar.setMinimumWidth(115)
        self.sidebar.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)

        self.sidebar_label = QLabel("Settings")
        self.sidebar_label.setAlignment(Qt.AlignCenter)
        self.sidebar_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.sidebar_label.setStyleSheet("font-size:18pt;")

        self.sidebar_spacer = QSpacerItem(5, 20)

        self.general_button = QPushButton("General")
        self.general_button.setCheckable(True)
        self.general_button.setChecked(True)
        self.general_button.toggled.connect(
            self.page_update_slot(self.general_page)
        )

        self.anki_button = QPushButton("Anki")
        self.anki_button.setCheckable(True)
        self.anki_button.toggled.connect(
            self.page_update_slot(self.anki_page)
        )

        self.audio_button = QPushButton("Audio")
        self.audio_button.setCheckable(True)
        self.audio_button.toggled.connect(
            self.page_update_slot(self.audio_page)
        )

        self.image_button = QPushButton("Image")
        self.image_button.setCheckable(True)
        self.image_button.toggled.connect(
            self.page_update_slot(self.image_page)
        )

        self.sidebar_buttons = QButtonGroup()
        self.sidebar_buttons.setExclusive(True)
        self.sidebar_buttons.addButton(self.general_button)
        self.sidebar_buttons.addButton(self.anki_button)
        self.sidebar_buttons.addButton(self.audio_button)
        self.sidebar_buttons.addButton(self.image_button)

        # Bottom buttons

        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self.update_settings)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_func)
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.ok_func)

        """
        Building Layout
        """

        self.sidebar_layout = QVBoxLayout()
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_layout.setSpacing(0)
        self.sidebar_layout.addWidget(self.sidebar_label)
        self.sidebar_layout.addItem(self.sidebar_spacer)
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

        self.setLayout(self.window_layout)

    def page_update_slot(self, widget):
        @Slot(bool)
        def update_page(checked):
            if checked:
                self.stacked_widget.setCurrentWidget(widget)
        return update_page

    def update_settings(self):
        self.anki_page.update_settings()
        self.general_page.update_settings()
        self.audio_page.update_settings()
        self.image_page.update_settings()

    def ok_func(self):
        self.update_settings()
        self.close()

    def cancel_func(self):
        self.close()
