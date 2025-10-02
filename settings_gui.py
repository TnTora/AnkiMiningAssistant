from datetime import timedelta
from PySide6.QtCore import (
    Qt,
)
from PySide6.QtWidgets import (
    QLineEdit,
    QWidget,
    QCheckBox,
    QComboBox,
    QLabel,
    QListWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QSlider,
    QSizePolicy,
    QSpinBox,
    QDoubleSpinBox,
    QStackedLayout,
    QTabWidget
)

from util.database import settings, get_attributes
import inspect


class SettingsWindow(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Settings")

        self.window_layout = QVBoxLayout()
        self.tab_widget = QTabWidget()
        self.window_layout.addWidget(self.tab_widget)

        for section, class_ in get_attributes(settings):
            if not inspect.isclass(class_):
                continue
            setattr(self, f"{section}_widget", QWidget())
            setattr(self, f"{section}_widget_layout", QVBoxLayout())

            setattr(self, f"{section}_label", QLabel(section))
            # self.window_layout.addWidget(getattr(self, f"{section}_label"))
            # getattr(self, f"{section}_widget_layout").addWidget(getattr(self, f"{section}_label"))
            for option, value in get_attributes(class_):
                setattr(self, f"{option}_layout", QHBoxLayout())
                setattr(self, f"{option}_label", QLabel(option))

                if isinstance(value, bool):
                    setattr(self, f"{option}_widget", QCheckBox())
                    if value:
                        getattr(self, f"{option}_widget").setCheckState(Qt.CheckState.Checked)
                elif isinstance(value, int):
                    setattr(self, f"{option}_widget", QSpinBox())
                    if value:
                        getattr(self, f"{option}_widget").setValue(value)
                elif isinstance(value, float):
                    setattr(self, f"{option}_widget", QDoubleSpinBox())
                    if value:
                        getattr(self, f"{option}_widget").setValue(value)
                elif isinstance(value, timedelta):
                    setattr(self, f"{option}_widget", QDoubleSpinBox())
                    if value:
                        getattr(self, f"{option}_widget").setValue(value.total_seconds())
                else:
                    setattr(self, f"{option}_widget", QLineEdit())
                    if value:
                        getattr(self, f"{option}_widget").setText(value)

                getattr(self, f"{option}_layout").addWidget(getattr(self, f"{option}_label"))
                getattr(self, f"{option}_layout").addWidget(getattr(self, f"{option}_widget"))
                # self.window_layout.addLayout(getattr(self, f"{option}_layout"))
                getattr(self, f"{section}_widget_layout").addLayout(getattr(self, f"{option}_layout"))

            getattr(self, f"{section}_widget").setLayout(getattr(self, f"{section}_widget_layout"))
            self.tab_widget.addTab(getattr(self, f"{section}_widget"), section)

        self.setLayout(self.window_layout)


