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

from util.audio import get_audio_inputs
from util.database import settings
from .custom_widgets import SettingItem, SettingsPage


class AudioPage(SettingsPage):

    settings_widgets = {}

    def __init__(self):  # noqa: PLR0915
        super().__init__()
        self.layout_rows = []

        # --------------------------------------------------------------------------------------
        # ------ Creating Widgets --------------------------------------------------------------
        # --------------------------------------------------------------------------------------

        # Samplerate
        self.samplerate_item = SettingItem("Samplerate")

        self.samplerate_spin = QSpinBox()
        self.samplerate_spin.setMaximum(100000)
        self.samplerate_spin.setMinimum(0)
        self.samplerate_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.samplerate_spin.setValue(settings.audio.samplerate)

        AudioPage.settings_widgets["samplerate"] = self.samplerate_spin
        self.layout_rows.append((self.samplerate_item, self.samplerate_spin))

        # Pause After Inactivity
        self.inactivity_item = SettingItem(
            name="Pause After Inactivity of",
            description="If no voice is detected for the time specified, "
                        "the buffer will not be updated until a new line is "
                        "received from a WebSocket or voice is detected once again.",
        )

        self.inactivity_spin = QSpinBox()
        self.inactivity_spin.setSuffix("s")
        self.inactivity_spin.setMaximum(int(settings.general.storage_time_limit.total_seconds()/2))
        self.samplerate_spin.setMinimum(0)
        self.inactivity_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.inactivity_spin.setValue(settings.audio.inactivity_pause_timer)

        AudioPage.settings_widgets["inactivity_pause_timer"] = self.inactivity_spin
        self.layout_rows.append((self.inactivity_item, self.inactivity_spin))

        # Continuous Recording
        self.continuous_recording_item = SettingItem(
            name="Continuous Recording",
            description="By default recordings are paused after the specified time of "
                        "voice inactivity. If this is toggled, recordings will not pause.",
        )

        self.continuous_recording_toggle = QCheckBox(" ")
        self.continuous_recording_toggle.setChecked(settings.audio.continuous_recording)

        AudioPage.settings_widgets["continuous_recording"] = self.continuous_recording_toggle
        self.layout_rows.append((self.continuous_recording_item, self.continuous_recording_toggle))

        # Preferred Audio Input
        self.audio_input_item = SettingItem(
            name="Preferred Audio Input",
            description="This setting will be used as the default when creating "
                        "a new session but can then be overwritten for each session.",
        )

        self.audio_input_combo = QComboBox()
        self.audio_input_combo.setMinimumWidth(150)
        self.audio_input_combo.setMaximumWidth(200)

        AudioPage.settings_widgets["audio_input"] = self.audio_input_combo
        self.layout_rows.append((self.audio_input_item, self.audio_input_combo))

        self.audio_input_combo.addItems([audio_input.name for audio_input in get_audio_inputs()[0]])
        self.audio_input_combo.setCurrentIndex(-1)

        if settings.audio.audio_input:
            self.audio_input_combo.setCurrentText(settings.audio.audio_input)

        # Vad Threshold
        self.vad_item = SettingItem(
            name="Vad Threshold",
        )

        self.vad_spin = QDoubleSpinBox()
        self.vad_spin.setMaximum(1)
        self.vad_spin.setMinimum(0)
        self.vad_spin.setSingleStep(0.05)
        self.vad_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.vad_spin.setValue(settings.audio.vad_threshold)

        AudioPage.settings_widgets["vad_threshold"] = self.vad_spin
        self.layout_rows.append((self.vad_item, self.vad_spin))

        # Padding
        self.padding_item = SettingItem(
            name="Padding",
            description="Padding added before and after the detected voice line.",
        )

        self.padding_spin = QSpinBox()
        self.padding_spin.setSuffix(" ms")
        self.padding_spin.setMaximum(1000)
        self.padding_spin.setMinimum(0)
        self.padding_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.padding_spin.setValue(settings.audio.padding)

        AudioPage.settings_widgets["padding"] = self.padding_spin
        self.layout_rows.append((self.padding_item, self.padding_spin))

        # --------------------------------------------------------------------------------------
        # ------ Building Layout ---------------------------------------------------------------
        # --------------------------------------------------------------------------------------

        for row, widgets in enumerate(self.layout_rows):
            self.main_layout.addWidget(widgets[0], row, 0, alignment=Qt.AlignmentFlag.AlignTop)
            self.main_layout.addWidget(widgets[1], row, 1, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        self.main_layout.setRowStretch(self.main_layout.rowCount(), 1)

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
