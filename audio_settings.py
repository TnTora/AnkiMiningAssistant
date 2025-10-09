from PySide6.QtCore import (
    Qt,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QScrollArea,
    QWidget,
    QLabel,
    QVBoxLayout,
    QSizePolicy,
    QSpinBox,
    QLineEdit,
    QDoubleSpinBox,
)

from util.audio import get_mics
from util.database import settings


def clear_layout(layout):

    for widget_no in range(0, layout.count()):
        if layout.itemAt(widget_no) is not None:
            if "Layout" not in str(layout.itemAt(widget_no)):
                layout.itemAt(widget_no).widget().deleteLater()
            else:
                clear_layout(layout.itemAt(widget_no))


class AudioPage(QWidget):

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

        self.samplerate_label = QLabel("Samplerate")
        self.samplerate_label.setStyleSheet(self.label_style)

        self.samplerate_spin = QSpinBox()
        self.samplerate_spin.setMaximum(100000)
        self.samplerate_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.samplerate_spin.setValue(settings.audio.samplerate)

        AudioPage.settings_widgets["samplerate"] = self.samplerate_spin

        self.inactivity_label = QLabel("Pause After Inactivity of")
        self.inactivity_label.setStyleSheet(self.label_style)

        self.inactivity_info = QLabel(
            "If no voice is detected for the time specified, "
            "the buffer will not be updated until a new line is "
            "received from a WebSocket or voice is detected once again."
        )
        self.inactivity_info.setWordWrap(True)
        self.inactivity_info.setStyleSheet(self.info_style)

        self.inactivity_spin = QSpinBox()
        self.inactivity_spin.setSuffix("s")
        self.inactivity_spin.setMaximum(int(settings.general.storage_time_limit.total_seconds()/2))
        self.inactivity_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.inactivity_spin.setValue(settings.audio.inactivity_pause_timer)

        AudioPage.settings_widgets["inactivity_pause_timer"] = self.inactivity_spin

        self.continuous_recording_label = QLabel("Continuous Recording")
        self.continuous_recording_label.setStyleSheet(self.label_style)

        self.continuous_recording_info = QLabel(
            "By default recordings are paused after the specified time of "
            "voice inactivity. If this is toggled, recordings will not pause."
        )
        self.continuous_recording_info.setWordWrap(True)
        self.continuous_recording_info.setStyleSheet(self.info_style)

        self.continuous_recording_toggle = QCheckBox(" ")
        self.continuous_recording_toggle.setChecked(settings.audio.continuous_recording)

        AudioPage.settings_widgets["continuous_recording"] = self.continuous_recording_toggle

        self.audio_input_label = QLabel("Preferred Audio Input")
        self.audio_input_label.setStyleSheet(self.label_style)

        self.audio_input_info = QLabel(
            "This setting will be used as the default when creating "
            "a new session but can then be overwritten for each session."
        )
        self.audio_input_info.setWordWrap(True)
        self.audio_input_info.setStyleSheet(self.info_style)

        self.audio_input_combo = QComboBox()
        self.audio_input_combo.setMinimumWidth(150)
        self.audio_input_combo.setMaximumWidth(200)

        AudioPage.settings_widgets["mic"] = self.audio_input_combo

        self.audio_input_combo.addItems([mic.name for mic in get_mics()[0]])

        self.audio_input_combo.setCurrentIndex(-1)

        if settings.audio.mic:
            self.audio_input_combo.setCurrentText(settings.audio.mic)

        """
        Building Layout
        """

        self.samplerate_layout = QVBoxLayout()
        self.samplerate_layout.addWidget(self.samplerate_label)

        self.inactivity_layout = QVBoxLayout()
        self.inactivity_layout.setSpacing(self.label_info_spacing)
        self.inactivity_layout.addWidget(self.inactivity_label)
        self.inactivity_layout.addWidget(self.inactivity_info)

        self.continuous_recording_layout = QVBoxLayout()
        self.continuous_recording_layout.setSpacing(self.label_info_spacing)
        self.continuous_recording_layout.addWidget(self.continuous_recording_label)
        self.continuous_recording_layout.addWidget(self.continuous_recording_info)

        self.audio_input_layout = QVBoxLayout()
        self.audio_input_layout.setSpacing(self.label_info_spacing)
        self.audio_input_layout.addWidget(self.audio_input_label, alignment=Qt.AlignTop)
        self.audio_input_layout.addWidget(self.audio_input_info, alignment=Qt.AlignTop)

        self.main_layout = QGridLayout()
        self.main_layout.setVerticalSpacing(30)
        self.main_layout.setContentsMargins(12, 12, 12, 12)

        self.main_layout.addLayout(self.samplerate_layout, 0, 0, alignment=Qt.AlignTop)
        self.main_layout.addWidget(self.samplerate_spin, 0, 1, alignment=Qt.AlignRight | Qt.AlignTop)

        self.main_layout.addLayout(self.inactivity_layout, 1, 0, alignment=Qt.AlignTop)
        self.main_layout.addWidget(self.inactivity_spin, 1, 1, alignment=Qt.AlignRight | Qt.AlignTop)

        self.main_layout.addLayout(self.continuous_recording_layout, 2, 0, alignment=Qt.AlignTop)
        self.main_layout.addWidget(self.continuous_recording_toggle, 2, 1, alignment=Qt.AlignRight | Qt.AlignTop)

        self.main_layout.addLayout(self.audio_input_layout, 3, 0, alignment=Qt.AlignTop)
        self.main_layout.addWidget(self.audio_input_combo, 3, 1, alignment=Qt.AlignRight | Qt.AlignTop)

        self.main_layout.setRowStretch(self.main_layout.rowCount(), 1)

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
        for option, wdg in AudioPage.settings_widgets.items():
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
            settings.update_option("audio", option, value)
