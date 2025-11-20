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

    def __init__(self):
        super().__init__()

        # --------------------------------------------------------------------------------------
        # ------ Creating Widgets --------------------------------------------------------------
        # --------------------------------------------------------------------------------------

        # Samplerate
        self.samplerate_item = SettingItem("Samplerate")

        self.samplerate_spin = QSpinBox()
        self.samplerate_spin.setMaximum(100000)
        self.samplerate_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.samplerate_spin.setValue(settings.audio.samplerate)

        AudioPage.settings_widgets["samplerate"] = self.samplerate_spin

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
        self.inactivity_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.inactivity_spin.setValue(settings.audio.inactivity_pause_timer)

        AudioPage.settings_widgets["inactivity_pause_timer"] = self.inactivity_spin

        # Continuous Recording
        self.continuous_recording_item = SettingItem(
            name="Continuous Recording",
            description="By default recordings are paused after the specified time of "
                        "voice inactivity. If this is toggled, recordings will not pause.",
        )

        self.continuous_recording_toggle = QCheckBox(" ")
        self.continuous_recording_toggle.setChecked(settings.audio.continuous_recording)

        AudioPage.settings_widgets["continuous_recording"] = self.continuous_recording_toggle

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

        self.audio_input_combo.addItems([audio_input.name for audio_input in get_audio_inputs()[0]])

        self.audio_input_combo.setCurrentIndex(-1)

        if settings.audio.audio_input:
            self.audio_input_combo.setCurrentText(settings.audio.audio_input)

        # --------------------------------------------------------------------------------------
        # ------ Building Layout ---------------------------------------------------------------
        # --------------------------------------------------------------------------------------

        self.main_layout.addWidget(self.samplerate_item, 0, 0, alignment=Qt.AlignTop)
        self.main_layout.addWidget(self.samplerate_spin, 0, 1, alignment=Qt.AlignRight | Qt.AlignTop)

        self.main_layout.addWidget(self.inactivity_item, 1, 0, alignment=Qt.AlignTop)
        self.main_layout.addWidget(self.inactivity_spin, 1, 1, alignment=Qt.AlignRight | Qt.AlignTop)

        self.main_layout.addWidget(self.continuous_recording_item, 2, 0, alignment=Qt.AlignTop)
        self.main_layout.addWidget(self.continuous_recording_toggle, 2, 1, alignment=Qt.AlignRight | Qt.AlignTop)

        self.main_layout.addWidget(self.audio_input_item, 3, 0, alignment=Qt.AlignTop)
        self.main_layout.addWidget(self.audio_input_combo, 3, 1, alignment=Qt.AlignRight | Qt.AlignTop)

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
