from PySide6.QtCore import (
    QSize,
    Qt,
)
from PySide6.QtWidgets import (
    QFormLayout,
    QGridLayout,
    QLineEdit,
    QToolButton,
    QWidget,
    QLabel,
    QVBoxLayout,
    QSizePolicy,
    QSpinBox,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
)

from util.database import settings
from .custom_widgets import SettingItem, SettingsPage


class GeneralPage(SettingsPage):

    settings_widgets = {}

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()

        # --------------------------------------------------------------------------------------
        # ------ Creating Widgets --------------------------------------------------------------
        # --------------------------------------------------------------------------------------

        # Buffer Length
        self.buffer_item = SettingItem(
            name="Buffer Length",
            description="Amount of time to store audio, images and lines",
        )


        self.buffer_spin = QSpinBox()
        self.buffer_spin.setMaximum(1800)
        self.buffer_spin.setSuffix("s")
        self.buffer_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.buffer_spin.setValue(settings.general.storage_time_limit.total_seconds())

        GeneralPage.settings_widgets["storage_time_limit"] = self.buffer_spin

        # WebSocket Port
        self.ws_port_item = SettingItem(
            name="WebSocket Port",
            description="PORT used to communicate with texthooker",
        )

        self.ws_port_spin = QSpinBox()
        self.ws_port_spin.setMaximum(65535)
        self.ws_port_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.ws_port_spin.setValue(settings.general.ws_port)

        GeneralPage.settings_widgets["ws_port"] = self.ws_port_spin

        # WebSockets Listeners
        self.listen_urls_item = SettingItem(
            name="Listen To WebSockets",
            description="URLs to listen to in order to receive text",
        )


        self.listen_urls = {}

        for url in settings.general.listen_urls:
            tmp_line_edit = QLabel(url)
            tmp_tool_button = QToolButton()

            tmp_tool_button.setText("-")
            tmp_tool_button.setMinimumSize(QSize(23, 22))

            tmp_tool_button.clicked.connect(lambda a, url=url: self.remove_listen_url(url))

            self.listen_urls[url] = [tmp_line_edit, tmp_tool_button]

        self.new_url_edit = QLineEdit()
        self.add_url_button = QToolButton()
        self.add_url_button.setText("+")
        self.add_url_button.setMinimumSize(QSize(23, 22))
        self.add_url_button.clicked.connect(self.add_listen_url)

        # --------------------------------------------------------------------------------------
        # ------ Building Layout ---------------------------------------------------------------
        # --------------------------------------------------------------------------------------

        self.urls_form = QFormLayout()
        self.urls_form.setContentsMargins(0, 0, 9, 0)
        self.urls_form.setVerticalSpacing(10)
        self.urls_form.setHorizontalSpacing(5)
        self.urls_form.setLabelAlignment(Qt.AlignRight)
        self.urls_form.setFormAlignment(Qt.AlignRight)
        for url in self.listen_urls:
            self.urls_form.addRow(self.listen_urls[url][0], self.listen_urls[url][1])
        self.urls_form.addRow(self.new_url_edit, self.add_url_button)

        self.main_layout.addWidget(self.buffer_item, 0, 0, alignment=Qt.AlignTop)
        self.main_layout.addWidget(self.buffer_spin, 0, 1, alignment=Qt.AlignRight | Qt.AlignTop)

        self.main_layout.addWidget(self.ws_port_item, 1, 0, alignment=Qt.AlignTop)
        self.main_layout.addWidget(self.ws_port_spin, 1, 1, alignment=Qt.AlignRight | Qt.AlignTop)

        self.main_layout.addWidget(self.listen_urls_item, 2, 0, alignment=Qt.AlignTop)
        self.main_layout.addLayout(self.urls_form, 2, 1, alignment=Qt.AlignRight | Qt.AlignTop)

        self.main_layout.setRowStretch(self.main_layout.rowCount(), 1)

    def add_listen_url(self):
        # TODO: Validate input
        new_url = self.new_url_edit.text()
        if not new_url:
            return
        new_line_edit = QLabel(new_url)
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

    def update_settings(self):
        for option, wdg in GeneralPage.settings_widgets.items():
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
            settings.update_option("general", option, value)

        tmp_listen_urls = list(self.listen_urls.keys())
        if tmp_listen_urls:
            settings.update_option("general", "listen_urls", tmp_listen_urls)
