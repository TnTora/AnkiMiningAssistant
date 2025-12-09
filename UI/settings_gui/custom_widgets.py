from PySide6.QtCore import (
    # QSize,
    Qt,
)
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QSizePolicy,
    QGridLayout,
    QScrollArea,
    QFrame,
)


class SettingItem(QWidget):

    def __init__(self, name, description: str | None = None) -> None:
        super().__init__()
        self.name = name
        self.description = description
        self.label_info_spacing = 4
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self.widget_layout = QVBoxLayout()
        self.widget_layout.setSpacing(self.label_info_spacing)
        self.widget_layout.setContentsMargins(0, 0, 0, 0)

        self.name_label = QLabel(self.name)
        self.name_label.setStyleSheet("font-size:13pt;")

        self.widget_layout.addWidget(self.name_label)

        if self.description is not None:
            self.description_label = QLabel(self.description)
            self.description_label.setWordWrap(True)
            self.description_label.setAlignment(Qt.AlignmentFlag.AlignTop)
            self.description_label.setStyleSheet("""
                font-size:9pt;
                font-weight:bold;
                color: #b4b4b4;
            """)
            self.widget_layout.addWidget(self.description_label)

        self.setLayout(self.widget_layout)


class SettingsPage(QWidget):

    def __init__(self):
        super().__init__()
        self.main_layout = QGridLayout()
        self.main_layout.setVerticalSpacing(30)
        self.main_layout.setContentsMargins(12, 12, 12, 12)

        self.scroll_content = QWidget()
        self.scroll_content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.scroll_content.setLayout(self.main_layout)

        self.scroll_area = QScrollArea()
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.scroll_content)

        self.outside_layout = QVBoxLayout()
        self.outside_layout.setContentsMargins(0, 0, 0, 0)
        self.outside_layout.addWidget(self.scroll_area)

        self.setLayout(self.outside_layout)
