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
)

from PIL import WebPImagePlugin
from util.database import settings


def clear_layout(layout):

    for widget_no in range(0, layout.count()):
        if layout.itemAt(widget_no) is not None:
            if "Layout" not in str(layout.itemAt(widget_no)):
                layout.itemAt(widget_no).widget().deleteLater()
            else:
                clear_layout(layout.itemAt(widget_no))


class ImagePage(QWidget):

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

        self.capture_interval_label = QLabel("Capture Interval")
        self.capture_interval_label.setStyleSheet(self.label_style)

        self.capture_interval_spin = QDoubleSpinBox()
        self.capture_interval_spin.setSuffix("s")
        self.capture_interval_spin.setMaximum(60)
        self.capture_interval_spin.setMinimum(1/60)
        self.capture_interval_spin.setSingleStep(0.01)
        self.capture_interval_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.capture_interval_spin.setValue(settings.image.capture_interval)

        ImagePage.settings_widgets["capture_interval"] = self.capture_interval_spin

        self.max_resolution_label = QLabel("Max Resolution")
        self.max_resolution_label.setStyleSheet(self.label_style)

        self.max_resolution_info = QLabel(
            "Limit the resolution of the screenshots."
        )
        self.max_resolution_info.setWordWrap(True)
        self.max_resolution_info.setStyleSheet(self.info_style)

        self.max_resolution_combo = QComboBox()
        self.max_resolution_combo.addItems(["1080p", "720p", "480p", "360p", "Native"])
        self.max_resolution_combo.setCurrentText(settings.image.max_resolution)
        # self.inactivity_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        ImagePage.settings_widgets["max_resolution"] = self.max_resolution_combo

        self.format_label = QLabel("Format")
        self.format_label.setStyleSheet(self.label_style)

        self.format_info = QLabel(
            "By default recordings are paused after the specified time of "
            "voice inactivity. If this is toggled, recordings will not pause."
        )
        self.format_info.setWordWrap(True)
        self.format_info.setStyleSheet(self.info_style)

        self.format_combo = QComboBox()
        self.available_formats = ["JPEG", "PNG"]
        if WebPImagePlugin.SUPPORTED:
            self.available_formats.append("WEBP")
        self.format_combo.addItems(self.available_formats)

        if settings.image.format in self.available_formats:
            self.format_combo.setCurrentText(settings.image.format)

        ImagePage.settings_widgets["format"] = self.format_combo

        """
        Building Layout
        """

        self.capture_interval_layout = QVBoxLayout()
        self.capture_interval_layout.addWidget(self.capture_interval_label)

        self.max_resolution_layout = QVBoxLayout()
        self.max_resolution_layout.setSpacing(self.label_info_spacing)
        self.max_resolution_layout.addWidget(self.max_resolution_label)
        self.max_resolution_layout.addWidget(self.max_resolution_info)

        self.format_layout = QVBoxLayout()
        self.format_layout.setSpacing(self.label_info_spacing)
        self.format_layout.addWidget(self.format_label)

        self.main_layout = QGridLayout()
        self.main_layout.setVerticalSpacing(30)
        self.main_layout.setContentsMargins(12, 12, 12, 12)

        self.main_layout.addLayout(self.capture_interval_layout, 0, 0)
        self.main_layout.addWidget(self.capture_interval_spin, 0, 1, alignment=Qt.AlignRight)

        self.main_layout.addLayout(self.max_resolution_layout, 1, 0)
        self.main_layout.addWidget(self.max_resolution_combo, 1, 1, alignment=Qt.AlignRight)

        self.main_layout.addLayout(self.format_layout, 2, 0, alignment=Qt.AlignTop)
        self.main_layout.addWidget(self.format_combo, 2, 1, alignment=Qt.AlignRight | Qt.AlignTop)

        self.scroll_content = QWidget()
        self.scroll_content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.scroll_content.setLayout(self.main_layout)

        self.scroll_area = QScrollArea()
        self.scroll_area.setAlignment(Qt.AlignTop)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.scroll_content)

        self.outside_layout = QVBoxLayout()
        self.outside_layout.setContentsMargins(0, 0, 0, 0)
        self.outside_layout.addWidget(self.scroll_area)

        self.setLayout(self.outside_layout)

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

