from PySide6.QtCore import (
    Qt,
    Signal,
    QObject,
    Slot,
    QSize,
    QRect,
    QPoint,
    # QTimer,
    QThreadPool,
    QRunnable,
)

from PySide6.QtGui import (
    QGuiApplication,
    QPixmap,
)

from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
    QSpinBox,
    QDoubleSpinBox,
    QSizePolicy,
    QStackedLayout,
)

from PIL import Image
from PIL.ImageQt import ImageQt
from time import sleep

from util.platform_util import capture_screenshot


class PixmapSignals(QObject):
    pixmap_update = Signal(object)


class ScreenshotWorker(QRunnable):

    def __init__(self, widget):
        super().__init__()
        self.widget = widget
        self.signals = PixmapSignals()
        self.stop_event = False

    def stop(self):
        self.stop_event = True

    @Slot()
    def run(self):
        try:
            while not self.stop_event:
                screen_region = self.widget.get_screen_region()
                print(f"{screen_region = }")
                img_bytesIO = capture_screenshot(None, None, screen_region, img_format="PNG", max_resolution=None)
                with Image.open(img_bytesIO) as img:
                    print(f"{img.size = }")
                    img.save(f"screenshots/{"_".join([str(a) for a in screen_region])}.png")
                    qimg = ImageQt(img)
                    img_pixmap = QPixmap.fromImage(qimg)
                self.signals.pixmap_update.emit(img_pixmap)
                sleep(1)
        except RuntimeError:
            self.stop()



class OffsetCalibration(QWidget):

    def __init__(self):
        super().__init__()
        self.instruction_label = QLabel(
            "Adjust x and y offsets until the image on the rigth"
            "matches the one on the left."
        )
        self.instruction_label.setWordWrap(True)
        self.instruction_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed)

        self.x_offset = QSpinBox()
        self.x_offset.setMinimum(-500)
        self.x_offset.setMaximum(500)
        self.x_offset.setPrefix("x offset: ")
        self.x_offset.setSuffix("px")
        self.x_offset.setValue(0)

        self.y_offset = QSpinBox()
        self.y_offset.setMinimum(-500)
        self.y_offset.setMaximum(500)
        self.y_offset.setPrefix("y offset: ")
        self.y_offset.setSuffix("px")
        self.y_offset.setValue(0)

        self.target = QLabel("Example")
        self.target.setAlignment(Qt.AlignCenter)
        self.target.setFixedSize(QSize(200, 200))
        self.target.setStyleSheet("background:#aa0000")

        self.monitor = QLabel()
        self.monitor.setFixedSize(QSize(200, 200))

        # -------------------------------------------------------------------------------------
        # -------- Building Layout ------------------------------------------------------------
        # -------------------------------------------------------------------------------------

        self.inputs_layout = QHBoxLayout()
        self.inputs_layout.addWidget(self.x_offset)
        self.inputs_layout.addWidget(self.y_offset)

        self.matching_layout = QHBoxLayout()
        self.matching_layout.addWidget(self.target)
        self.matching_layout.addWidget(self.monitor)

        self.main_layout = QVBoxLayout()
        self.main_layout.addWidget(self.instruction_label)
        self.main_layout.addLayout(self.inputs_layout)
        self.main_layout.addLayout(self.matching_layout)
        self.main_layout.setStretch(2, 1)

        self.setLayout(self.main_layout)

    def get_screen_region(self):
        top_left = self.target.mapToGlobal(QPoint(0, 0))
        bot_right = self.target.mapToGlobal(QPoint(self.target.geometry().width(), self.target.geometry().height()))
        screen_region = (
            top_left.x()+self.x_offset.value(),
            top_left.y()+self.y_offset.value(),
            bot_right.x()+self.x_offset.value(),
            bot_right.y()+self.y_offset.value(),
        )
        print(f"{self.target.geometry().topLeft() = }\n{self.target.geometry().bottomRight() = }\n{screen_region = }")
        return screen_region

    def update_pixmap(self, pixmap):
        self.monitor.setPixmap(pixmap)


class ScalingCalibration(QWidget):

    def __init__(self):
        super().__init__()
        self.pixel_ratio = QGuiApplication.primaryScreen().devicePixelRatio()

        self.instruction_label = QLabel(
            "Adjust scaling until the image shows the entire screen"
        )
        self.instruction_label.setWordWrap(True)
        self.instruction_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed)

        self.scaling = QDoubleSpinBox()
        self.scaling.setMinimum(0.1)
        self.scaling.setMaximum(6)
        self.scaling.setSingleStep(0.05)
        self.scaling.setPrefix("Scaling: ")
        self.scaling.setSuffix("x")
        self.scaling.setValue(1)

        self.monitor = QLabel()
        self.monitor.setFixedWidth(400)
        self.monitor.setStyleSheet("border: 1px solid black;")

        # -------------------------------------------------------------------------------------
        # -------- Building Layout ------------------------------------------------------------
        # -------------------------------------------------------------------------------------

        self.main_layout = QVBoxLayout()
        self.main_layout.setAlignment(Qt.AlignHCenter)
        self.main_layout.addWidget(self.instruction_label)
        self.main_layout.addWidget(self.scaling)
        self.main_layout.addWidget(self.monitor)
        self.main_layout.setStretch(2, 1)

        self.setLayout(self.main_layout)

    def get_screen_region(self):
        screen_region = QGuiApplication.primaryScreen().geometry().getCoords()
        screen_region = tuple(int(self.scaling.value()*a) for a in screen_region)
        return screen_region

    def update_pixmap(self, pixmap):
        pixmap = pixmap.scaledToWidth(self.monitor.size().width(), mode=Qt.TransformationMode.SmoothTransformation)
        self.monitor.setPixmap(pixmap)


class CalibrationDialog(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Screen Region Calibration")
        self.setFixedSize(QSize(500, 500))

        self.scaling_widget = ScalingCalibration()
        self.offsets_widget = OffsetCalibration()

        self.curr_widget = self.offsets_widget

        # -------------------------------------------------------------------------------------
        # -------- Building Layout ------------------------------------------------------------
        # -------------------------------------------------------------------------------------

        self.main_layout = QStackedLayout()
        self.main_layout.addWidget(self.scaling_widget)
        self.main_layout.addWidget(self.offsets_widget)

        self.main_layout.setCurrentWidget(self.curr_widget)

        self.setLayout(self.main_layout)

        # -------------------------------------------------------------------------------------
        # -------- Extra ----------------------------------------------------------------------
        # -------------------------------------------------------------------------------------

        # self.update_timer = QTimer(self)
        # self.update_timer.setInterval(1000)
        # self.update_timer.timeout.connect(
        #     lambda: self.get_screen_region(self.scaling_widget)
        # )
        # self.update_timer.start()
        self.threadpool = QThreadPool()
        self.screenshot_worker = ScreenshotWorker(self.curr_widget)
        self.screenshot_worker.signals.pixmap_update.connect(
            self.curr_widget.update_pixmap
        )
        self.threadpool.start(self.screenshot_worker)

    def closeEvent(self, event):
        if not self.screenshot_worker.stop_event:
            self.screenshot_worker.stop()

    def update_pixmap(self, screen_region: tuple, label_widget: QLabel, scale_width: int | None = None):
        img_bytesIO = capture_screenshot(None, None, screen_region, img_format="PNG")
        with Image.open(img_bytesIO) as img:
            qimg = ImageQt(img)
            img_pixmap = QPixmap.fromImage(qimg)
            if scale_width:
                img_pixmap = img_pixmap.scaledToWidth(scale_width, mode=Qt.TransformationMode.SmoothTransformation)
            label_widget.setPixmap(img_pixmap)

    def get_screen_region(self, widget):
        screen_region, width = widget.get_screen_region()
        self.update_pixmap(screen_region, widget.monitor, width)

