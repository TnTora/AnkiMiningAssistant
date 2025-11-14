from PySide6.Core import (
    Qt,
    Signal,
    QSize,
    QRect,
)

from PySide6.QtGui import QGuiApplication

from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
    QSpinBox,
    QDoubleSpinBox,
)


class CalibrationDialog(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Screen Region Calibration")
        self.setFixedSize(QSize(500, 500))

        self.pixel_ratio = QGuiApplication.primaryScreen().devicePixelRatio()

        self.instruction_label = QLabel(
            "Adjust x, y offsets and scaling until the image on the rigth"
            "matches the one on the left."
        )
        self.instruction_label.setWordWrap(True)

        self.x_offset = QSpinBox()
        self.x_offset.setMinimum(0)
        self.x_offset.setMaximum(500)
        self.x_offset.setSuffix("px")
        self.x_offset.setValue(0)

        self.y_offset = QSpinBox()
        self.y_offset.setMinimum(0)
        self.y_offset.setMaximum(500)
        self.y_offset.setSuffix("px")
        self.y_offset.setValue(0)

        self.scaling = QDoubleSpinBox()
        self.scaling.setMinimum(0.1)
        self.scaling.setMaximum(6)
        self.scaling.setSuffix("x")
        self.scaling.setValue(self.pixel_ratio)
