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

    settings_widgets = {}

    def __init__(self):
        super().__init__()
        self.calibration_window = None
        self.layout_rows = []

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
        self.layout_rows.append((self.capture_interval_item, self.capture_interval_spin))

        # Max Resolution
        self.max_resolution_item = SettingItem(
            name="Max Resolution",
            description="Limit the resolution of the screenshots.",
        )

        self.max_resolution_combo = QComboBox()
        self.max_resolution_combo.addItems(["1080p", "720p", "480p", "360p", "Native"])
        self.max_resolution_combo.setCurrentText(settings.image.max_resolution)

        ImagePage.settings_widgets["max_resolution"] = self.max_resolution_combo
        self.layout_rows.append((self.max_resolution_item, self.max_resolution_combo))

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
        self.layout_rows.append((self.format_item, self.format_combo))

        # Screen Region Calibration
        self.calibration_item = SettingItem(
            name="Screen Region Calibration",
            description="Calibrate screen region screenshot by selecting "
                        "window scaling and (x, y) offsets.",
        )

        self.calibration_button = QPushButton("Calibrate")
        self.calibration_button.clicked.connect(self.open_calibration_window)

        self.layout_rows.append((self.calibration_item, self.calibration_button))

        # --------------------------------------------------------------------------------------
        # ------ Building Layout ---------------------------------------------------------------
        # --------------------------------------------------------------------------------------

        for row, widgets in enumerate(self.layout_rows):
            self.main_layout.addWidget(widgets[0], row, 0, alignment=Qt.AlignTop)
            self.main_layout.addWidget(widgets[1], row, 1, alignment=Qt.AlignRight | Qt.AlignTop)

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

