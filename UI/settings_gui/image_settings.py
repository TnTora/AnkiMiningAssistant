from PySide6.QtCore import (
    Qt,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QScrollArea,
    QWidget,
    QLabel,
    QVBoxLayout,
    QSizePolicy,
    QSpinBox,
    QLineEdit,
    QCheckBox,
    QPushButton,
)

from PIL import WebPImagePlugin
from util.database import settings
from UI.custom_widgets import CalibrationDialog
from .custom_widgets import SettingItem, SettingsPage


class ImagePage(SettingsPage):

    label_style = "font-size:13pt;"
    info_style = """
            font-size:9pt;
            font-weight:bold;
            color: #b4b4b4;
        """

    label_info_spacing = 4

    settings_widgets = {}

    def __init__(self):
        super().__init__()
        self.calibration_window = None

        # --------------------------------------------------------------------------------------
        # ------ Creating Widgets --------------------------------------------------------------
        # --------------------------------------------------------------------------------------

        # Capture Interval
        self.capture_interval_item = SettingItem("Capture Interval")

        self.capture_interval_spin = QDoubleSpinBox()
        self.capture_interval_spin.setSuffix("s")
        self.capture_interval_spin.setMaximum(60)
        self.capture_interval_spin.setMinimum(1/60)
        self.capture_interval_spin.setSingleStep(0.01)
        self.capture_interval_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.capture_interval_spin.setValue(settings.image.capture_interval)

        ImagePage.settings_widgets["capture_interval"] = self.capture_interval_spin

        # Max Resolution
        self.max_resolution_item = SettingItem(
            name="Max Resolution",
            description="Limit the resolution of the screenshots.",
        )

        self.max_resolution_combo = QComboBox()
        self.max_resolution_combo.addItems(["1080p", "720p", "480p", "360p", "Native"])
        self.max_resolution_combo.setCurrentText(settings.image.max_resolution)
        # self.inactivity_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        ImagePage.settings_widgets["max_resolution"] = self.max_resolution_combo

        # Format
        self.format_item = SettingItem(
            name="Format",
            description="By default recordings are paused after the specified time of "
                        "voice inactivity. If this is toggled, recordings will not pause.",
        )

        self.format_combo = QComboBox()
        self.available_formats = ["JPEG", "PNG"]
        if WebPImagePlugin.SUPPORTED:
            self.available_formats.append("WEBP")
        self.format_combo.addItems(self.available_formats)

        if settings.image.format in self.available_formats:
            self.format_combo.setCurrentText(settings.image.format)

        ImagePage.settings_widgets["format"] = self.format_combo

        # Screen Region Calibration
        self.calibration_item = SettingItem(
            name="Screen Region Calibration",
            description="Calibrate screen region screenshot by selecting "
                        "window scaling and (x, y) offsets.",
        )

        self.calibration_button = QPushButton("Calibrate")
        self.calibration_button.clicked.connect(self.open_calibration_window)

        # --------------------------------------------------------------------------------------
        # ------ Building Layout ---------------------------------------------------------------
        # --------------------------------------------------------------------------------------

        self.main_layout.addWidget(self.capture_interval_item, 0, 0, alignment=Qt.AlignTop)
        self.main_layout.addWidget(self.capture_interval_spin, 0, 1, alignment=Qt.AlignRight | Qt.AlignTop)

        self.main_layout.addWidget(self.max_resolution_item, 1, 0, alignment=Qt.AlignTop)
        self.main_layout.addWidget(self.max_resolution_combo, 1, 1, alignment=Qt.AlignRight | Qt.AlignTop)

        self.main_layout.addWidget(self.format_item, 2, 0, alignment=Qt.AlignTop)
        self.main_layout.addWidget(self.format_combo, 2, 1, alignment=Qt.AlignRight | Qt.AlignTop)

        self.main_layout.addWidget(self.calibration_item, 3, 0, alignment=Qt.AlignTop)
        self.main_layout.addWidget(self.calibration_button, 3, 1, alignment=Qt.AlignRight | Qt.AlignTop)

        self.main_layout.setRowStretch(self.main_layout.rowCount(), 1)

    def open_calibration_window(self):
        self.calibration_window = CalibrationDialog()
        self.calibration_window.show()

    def update_settings(self):
        for option, wdg in ImagePage.settings_widgets.items():
            if isinstance(wdg, (QSpinBox, QDoubleSpinBox)):
                value = wdg.value()
            elif isinstance(wdg, QLineEdit):
                value = wdg.text()
                if not value:
                    continue
            elif isinstance(wdg, QCheckBox):
                value = wdg.isChecked()
            elif isinstance(wdg, QComboBox):
                value = wdg.currentText()
                if not value:
                    continue
            settings.update_option("image", option, value)

