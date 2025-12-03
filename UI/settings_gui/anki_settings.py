from PySide6.QtCore import (
    QSize,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QScrollArea,
    QToolButton,
    QWidget,
    QLabel,
    QVBoxLayout,
    QSizePolicy,
    QSpinBox,
    QDoubleSpinBox,
)

from time import sleep
from threading import Thread, Event

from util.anki import (
    get_all_note_types_fields,
    get_note_types,
    get_media_dir,
)
from util.database import settings
from .custom_widgets import SettingItem, SettingsPage

import logging

logger = logging.getLogger("app_logger")


class NoteTypesForm(QWidget):

    note_removed = Signal(str)
    note_added = Signal(str)

    def __init__(self, note_types: dict) -> None:
        super().__init__()

        self.note_types_dict = note_types

        self.notes_form = QFormLayout()
        self.notes_form.setContentsMargins(0, 0, 9, 0)
        self.notes_form.setVerticalSpacing(10)
        self.notes_form.setHorizontalSpacing(5)
        self.notes_form.setLabelAlignment(Qt.AlignRight)
        self.notes_form.setFormAlignment(Qt.AlignRight)

        for note in settings.anki.note_types:
            tmp_label = QLabel(f"{note} ")
            tmp_tool_button = QToolButton()

            tmp_tool_button.setText("-")
            tmp_tool_button.setMinimumSize(QSize(23, 22))
            tmp_tool_button.clicked.connect(self.remove_note_slot_gen(note))

            self.note_types_dict[note] = [tmp_label, tmp_tool_button]

            self.notes_form.addRow(tmp_label, tmp_tool_button)

        self.new_note_combo = QComboBox()
        self.new_note_combo.setMaximumWidth(200)

        if settings.anki.note_types_fields:
            note_types_db = list(settings.anki.note_types_fields.keys())
            self.new_note_combo.addItems(note_types_db)

        self.new_note_combo.setCurrentIndex(-1)

        self.add_note_button = QToolButton()
        self.add_note_button.setText("+")
        self.add_note_button.setMinimumSize(QSize(23, 22))
        self.add_note_button.clicked.connect(self.add_note_type)

        self.notes_form.addRow(self.new_note_combo, self.add_note_button)

        self.setLayout(self.notes_form)

    def remove_note_slot_gen(self, note):
        @Slot()
        def remove_note():
            row = self.note_types_dict.pop(note)
            self.notes_form.removeRow(row[1])
            # self.remove_note_field_row(note)
            self.note_removed.emit(note)
        return remove_note

    def add_note_type(self):
        new_note = self.new_note_combo.currentText()
        if not new_note:
            return
        new_label = QLabel(f"{new_note} ")
        new_button = QToolButton()
        new_button.setText("-")
        new_button.setMinimumSize(QSize(23, 22))
        new_button.clicked.connect(self.remove_note_slot_gen(new_note))
        self.notes_form.takeRow(self.add_note_button)
        self.note_types_dict[new_note] = [new_label, new_button]
        self.notes_form.addRow(new_label, new_button)
        self.new_note_combo.setCurrentIndex(-1)
        self.notes_form.addRow(self.new_note_combo, self.add_note_button)
        # self.add_note_fields_row(new_note)
        self.note_added.emit(new_note)


class NoteTypeFields(QWidget):

    def __init__(self, note_type: str, card_fields: list, note_types_fields: dict) -> None:
        super().__init__()
        self.note_type = note_type
        self.card_fields = card_fields
        self.note_types_fields = note_types_fields

        self.form_widget = QWidget()

        self.form_layout = QFormLayout()
        self.form_layout.setLabelAlignment(Qt.AlignLeft)
        self.form_layout.setFormAlignment(Qt.AlignRight)
        self.form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.form_layout.setContentsMargins(10, 0, 0, 0)
        self.form_layout.setHorizontalSpacing(70)
        self.form_widget.setLayout(self.form_layout)
        self.form_widget.setStyleSheet("""
            border-left:1px solid gray;
        """)
        self.form_widget.setMinimumHeight(110)

        for field in self.card_fields:
            tmp_combo = QComboBox()

            # if AnkiPage.found_note_types_fields is not None and AnkiPage.found_note_types_fields[note]:
            #     tmp_combo.addItems(AnkiPage.found_note_types_fields[note])
            if settings.anki.note_types_fields and settings.anki.note_types_fields[note_type]:
                tmp_combo.addItems(settings.anki.note_types_fields[note_type])

            tmp_combo.setCurrentIndex(-1)
            if note_type in settings.anki.note_types:
                text = getattr(settings.anki, field.lower().replace(" ", "_"))[note_type]
                tmp_combo.setCurrentText(text)

            self.form_layout.addRow(field, tmp_combo)
            self.note_types_fields[note_type][field] = tmp_combo

        # self.note_types_fields[note_type]["widget"] = self.form_widget

        self.h_box = QHBoxLayout()
        self.h_box.setContentsMargins(13, 0, 0, 0)
        self.note_label = QLabel(note_type)
        self.note_label.setMinimumWidth(80)
        self.note_label.setWordWrap(True)
        self.note_label.setAlignment(Qt.AlignCenter)
        self.h_box.addWidget(self.note_label)
        self.h_box.addWidget(self.form_widget)
        self.h_box.setStretch(1, 1)

        self.setLayout(self.h_box)


class AnkiPage(SettingsPage):

    settings_widgets = {}

    def __init__(self):  # noqa: PLR0915
        super().__init__()
        self.layout_rows = []

        # --------------------------------------------------------------------------------------
        # ------ Creating Widgets --------------------------------------------------------------
        # --------------------------------------------------------------------------------------

        # Anki Port
        self.anki_port_item = SettingItem(
            "AnkiConnect PORT",
            description="Once connected the following options will become available"
        )

        self.anki_port_spin = QSpinBox()
        self.anki_port_spin.setMaximum(65535)
        self.anki_port_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.anki_port_spin.setValue(settings.anki.port)
        self.anki_port_spin.valueChanged.connect(self.update_anki_port)

        AnkiPage.settings_widgets["port"] = self.anki_port_spin
        self.layout_rows.append((self.anki_port_item, self.anki_port_spin))

        # Media Directory
        self.media_item = SettingItem("Media Directory")

        self.media_line_edit = QLineEdit()
        self.media_line_edit.setMinimumWidth(200)
        self.media_line_edit.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

        self.media_select = QFileDialog()
        self.media_select.setFileMode(QFileDialog.FileMode.Directory)
        if settings.anki.media_dir is not None:
            self.media_select.setDirectory(settings.anki.media_dir)
        self.media_select.fileSelected.connect(self.update_dir)

        self.media_button = QToolButton()
        self.media_button.setMinimumSize(QSize(23, 22))
        self.media_button.setText("...")
        self.media_button.clicked.connect(self.media_select.open)

        if settings.anki.media_dir:
            self.media_line_edit.setText(settings.anki.media_dir)

        self.media_edit_layout = QHBoxLayout()
        self.media_edit_layout.addWidget(self.media_line_edit)
        self.media_edit_layout.addWidget(self.media_button)

        self.media_widget = QWidget()
        self.media_widget.setLayout(self.media_edit_layout)

        AnkiPage.settings_widgets["media_dir"] = self.media_line_edit
        self.layout_rows.append((self.media_item, self.media_widget))

        # Deck
        self.deck_item = SettingItem(
            name="Deck",
            description="Which deck will be automatically monitored for new cards. "
                        "* will monitor all decks.",
        )

        self.deck_line_edit = QLineEdit()
        self.deck_line_edit.setText(settings.anki.deck)

        AnkiPage.settings_widgets["deck"] = self.deck_line_edit
        self.layout_rows.append((self.deck_item, self.deck_line_edit))

        # Auto Update
        self.auto_update_item = SettingItem(
            name="Auto Update Note",
            description="Update note as soon as it is added to Anki. "
                        "This setting can be overwritten for each session.",
        )

        self.auto_update_toggle = QCheckBox(" ")
        self.auto_update_toggle.setChecked(settings.anki.auto_update_last_note)

        AnkiPage.settings_widgets["auto_update_last_note"] = self.auto_update_toggle
        self.layout_rows.append((self.auto_update_item, self.auto_update_toggle))

        # Open in GUI
        self.open_in_gui_item = SettingItem(
            name="Open Updated Note in Browser",
            description="When a note is updated, show it in the anki browser. "
                        "This setting can be overwritten for each session.",
        )

        self.open_in_gui_toggle = QCheckBox(" ")
        self.open_in_gui_toggle.setChecked(settings.anki.open_note_in_gui)

        AnkiPage.settings_widgets["open_note_in_gui"] = self.open_in_gui_toggle
        self.layout_rows.append((self.open_in_gui_item, self.open_in_gui_toggle))

        # Note Types
        self.note_types_item = SettingItem(
            name="Note Types",
            description="Which note types can be updated",
        )

        self.note_types = {}

        self.note_types_form = NoteTypesForm(self.note_types)

        AnkiPage.settings_widgets["note_types"] =  self.note_types_form.new_note_combo
        self.layout_rows.append((self.note_types_item, self.note_types_form))

        self.note_types_fields = {}
        self.card_fields = ["Expression", "Sentence", "Sentence Audio", "Picture"]

        # --------------------------------------------------------------------------------------
        # ------ Building Layout ---------------------------------------------------------------
        # --------------------------------------------------------------------------------------

        for row, widgets in enumerate(self.layout_rows):
            self.main_layout.addWidget(widgets[0], row, 0, alignment=Qt.AlignTop)
            self.main_layout.addWidget(widgets[1], row, 1, alignment=Qt.AlignRight | Qt.AlignTop)

        for note in self.note_types:
            self.add_note_fields_row(note)

        # --------------------------------------------------------------------------------------
        # ------ Extra -------------------------------------------------------------------------
        # --------------------------------------------------------------------------------------

        self.note_types_form.note_added.connect(self.add_note_fields_row)
        self.note_types_form.note_removed.connect(self.remove_note_field_row)

        self.thread_stop = Event()
        self.anki_thread = Thread(target=self.get_anki_info, daemon=True)
        self.anki_thread.start()

    def add_note_fields_row(self, note):
        self.note_types_fields[note] = {}
        tmp_fields_widget = NoteTypeFields(note, self.card_fields, self.note_types_fields)
        self.note_types_fields[note]["widget"] = tmp_fields_widget
        new_row = self.main_layout.rowCount()
        self.main_layout.addWidget(tmp_fields_widget, new_row, 0, 1, 2, alignment=Qt.AlignTop)

        # Add stretch to just the last row to keep everything top aligned
        self.main_layout.setRowStretch(new_row - 1, 0)
        self.main_layout.setRowStretch(new_row, 1)

    def remove_note_field_row(self, note):
        self.main_layout.removeWidget(self.note_types_fields[note]["widget"])
        self.note_types_fields[note]["widget"].deleteLater()
        self.note_types_fields.pop(note)

    def get_anki_info(self):  # noqa: C901
        while True:
            try:
                if self.thread_stop.is_set():
                    break

                if settings.anki.media_dir is None:
                    media_dir = get_media_dir()
                    if media_dir is None:
                        continue
                    settings.update_option("anki", "media_dir", media_dir)
                    self.media_line_edit.setText(settings.anki.media_dir)

                note_types = get_note_types()
                fields = get_all_note_types_fields(note_types)
                if fields is None:
                    continue

                old_idx = self.note_types_form.new_note_combo.currentIndex()
                self.note_types_form.new_note_combo.clear()
                self.note_types_form.new_note_combo.addItems(note_types)
                self.note_types_form.new_note_combo.setCurrentIndex(old_idx)

                settings.anki.note_types_fields = fields

                for note_type in self.note_types_fields:
                    for field in self.note_types_fields[note_type]:
                        if field == "widget":
                            continue
                        tmp_combo = self.note_types_fields[note_type][field]
                        old_idx = tmp_combo.currentIndex()
                        tmp_combo.clear()
                        tmp_combo.addItems(fields[note_type])
                        tmp_combo.setCurrentIndex(old_idx)
                        if note_type in settings.anki.note_types:
                            text = getattr(settings.anki, field.lower().replace(" ", "_"))[note_type]
                            tmp_combo.setCurrentText(text)
                break
            except Exception as e:
                # TODO: specify exceptions
                logger.warning("AnkiSettings: %s", e)
            finally:
                sleep(0.3)

    def update_anki_port(self, port: int) -> None:
        settings.update_option("anki", "port", port)

    def update_dir(self, file) -> None:
        if not file:
            return
        self.media_line_edit.setText(file)
        self.media_select.setDirectory(file)

    def update_note_types_fields(self) -> list:
        tmp_fields = {field.lower().replace(" ", "_"): {} for field in self.card_fields}
        tmp_note_types = list(self.note_types.keys())
        settings.update_option("anki", "note_types", tmp_note_types)

        missing_fields = []

        for note in self.note_types_fields:
            for field, wdg in self.note_types_fields[note].items():
                if field == "widget":
                    continue
                tmp_text = wdg.currentText()
                if not tmp_text:
                    missing_fields.append(field)
                    continue
                tmp_fields[field.lower().replace(" ", "_")][note] = tmp_text

        if missing_fields:
            return missing_fields

        for field, value in tmp_fields.items():
            settings.update_option("anki", field, value)


    def update_settings(self) -> list:
        for option, wdg in AnkiPage.settings_widgets.items():
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
            settings.update_option("anki", option, value)

        missing_fields = self.update_note_types_fields()
        return missing_fields
