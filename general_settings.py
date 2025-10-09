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
)

from util.database import settings


class GeneralPage(QWidget):

    label_style = "font-size:13pt;"
    info_style = """
            font-size:9pt;
            font-weight:bold;
            color: #b4b4b4;
        """

    label_info_spacing = 4

    def __init__(self):
        super().__init__()

        self.buffer_label = QLabel("Buffer Length")
        self.buffer_label.setStyleSheet(self.label_style)

        self.buffer_info = QLabel("Amount of time to store audio, images and lines")
        self.buffer_info.setWordWrap(True)
        self.buffer_info.setStyleSheet(self.info_style)

        self.buffer_spin = QSpinBox()
        self.buffer_spin.setMaximum(1800)
        self.buffer_spin.setSuffix("s")
        self.buffer_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.ws_port_label = QLabel("WebSocket Port")
        self.ws_port_label.setStyleSheet(self.label_style)

        self.ws_port_spin = QSpinBox()
        self.ws_port_spin.setMaximum(65535)
        self.ws_port_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.ws_port_info = QLabel("PORT used to communicate with texthooker")
        self.ws_port_info.setWordWrap(True)
        self.ws_port_info.setStyleSheet(self.info_style)

        self.listen_urls_label = QLabel("Listen To WebSockets")
        self.listen_urls_label.setStyleSheet(self.label_style)

        self.listen_urls_info = QLabel("URLs to listen to in order to receive text")
        self.listen_urls_info.setWordWrap(True)
        self.listen_urls_info.setStyleSheet(self.info_style)

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
        self.buffer_layout.setSpacing(self.label_info_spacing)
        self.buffer_layout.addWidget(self.buffer_label)
        self.buffer_layout.addWidget(self.buffer_info)

        self.ws_port_layout = QVBoxLayout()
        self.ws_port_layout.setSpacing(self.label_info_spacing)
        self.ws_port_layout.addWidget(self.ws_port_label)
        self.ws_port_layout.addWidget(self.ws_port_info)

        self.listen_urls_layout = QVBoxLayout()
        self.listen_urls_layout.setSpacing(self.label_info_spacing)
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
