from PySide6.QtCore import (
    Qt,
    Signal,
    QObject,
    Slot,
    QSize,
    QRect,
    QPoint,
    QThreadPool,
    QRunnable,
)

from PySide6.QtGui import (
    QGuiApplication,
    QPixmap,
    QColor,
)

from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QPushButton,
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

from util.platform_util import capture_screenshot, is_wayland
from .RegionSelect import RegionSelect
from util.database import settings


class ManualSelection(RegionSelect):

    def __init__(self, offsets_widget: QWidget):
        super().__init__(0, 0, offsets_widget.target.size().width(), offsets_widget.target.size().height())
        self.selection_color = QColor(0, 0, 0, 1)
        self.offsets_widget = offsets_widget

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        pos = event.pos()
        if self.selection.contains(pos, proper=True):
            self.pressed = "center"
            self.old_mouse_pos = pos

    def save_selection(self):
        coords = self.selection.normalized().getCoords()
        img_bytesIO = capture_screenshot(img_format="PNG", max_resolution=None)

        self.offsets_widget.img = Image.open(img_bytesIO).resize((self.screen_geometry.width(), self.screen_geometry.height()))
        self.offsets_widget.coords = coords
        self.offsets_widget.update_pixmap(crop=True)

        self.offsets_widget.instruction_label.setText(
            "Adjust x and y offsets until the image on the rigth "
            "matches the one on the left."
        )

        self.close()



class PixmapSignals(QObject):
    pixmap_update = Signal(object)


class ScreenshotWorker(QRunnable):

    def __init__(self, widget):
        super().__init__()
        self.widget = widget
        self.signals = PixmapSignals()

    @Slot()
    def run(self):
        screen_region = self.widget.get_screen_region()
        # print(f"{screen_region = }")
        img_bytesIO = capture_screenshot(None, None, screen_region, img_format="PNG", max_resolution=None)
        with Image.open(img_bytesIO) as img:
            # print(f"{img.size = }")
            qimg = ImageQt(img)
            img_pixmap = QPixmap.fromImage(qimg)
        self.signals.pixmap_update.emit(img_pixmap)



class OffsetCalibration(QWidget):

    def __init__(self):
        super().__init__()
        self.img = None
        self.coords = None
        self.pixel_ratio = None
        self.manual_selection = None

        self.instruction_label = QLabel(
            "Click the Screenshot button and align the selection with "
            "the square on the left."
        )
        self.instruction_label.setWordWrap(True)
        self.instruction_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed)

        self.screenshot_button = QPushButton("Take Screenshot")
        self.screenshot_button.clicked.connect(self.open_manual_selection)

        self.x_offset = QSpinBox()
        self.x_offset.setMinimum(-500)
        self.x_offset.setMaximum(500)
        self.x_offset.setPrefix("x offset: ")
        self.x_offset.setSuffix("px")
        self.x_offset.setValue(settings.image.offsets["x"])
        self.x_offset.valueChanged.connect(
            self.update_pixmap_slot
        )

        self.y_offset = QSpinBox()
        self.y_offset.setMinimum(-500)
        self.y_offset.setMaximum(500)
        self.y_offset.setPrefix("y offset: ")
        self.y_offset.setSuffix("px")
        self.y_offset.setValue(settings.image.offsets["y"])
        self.y_offset.valueChanged.connect(
            self.update_pixmap_slot
        )

        self.target = QLabel("Example")
        self.target.setAlignment(Qt.AlignCenter)
        self.target.setFixedSize(QSize(200, 200))
        self.target.setStyleSheet("""
            background:#aa0000;
            border: 1px solid black;
        """)

        self.monitor = QLabel()
        self.monitor.setFixedSize(QSize(200, 200))
        self.monitor.setStyleSheet("border: 1px solid black;")

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
        self.main_layout.addWidget(self.screenshot_button)
        self.main_layout.addLayout(self.inputs_layout)
        self.main_layout.addLayout(self.matching_layout)
        self.main_layout.setStretch(2, 1)

        self.setLayout(self.main_layout)

    def open_manual_selection(self):
        self.manual_selection = ManualSelection(self)
        self.manual_selection.show()

    def get_screen_region(self):
        top_left = self.target.mapToGlobal(QPoint(0, 0))
        bot_right = self.target.mapToGlobal(QPoint(self.target.geometry().width(), self.target.geometry().height()))
        screen_region = (
            top_left.x()+self.x_offset.value(),
            top_left.y()+self.y_offset.value(),
            bot_right.x()+self.x_offset.value(),
            bot_right.y()+self.y_offset.value(),
        )
        self.coords = screen_region
        print(f"{self.target.geometry().topLeft() = }\n{self.target.geometry().bottomRight() = }\n{screen_region = }")
        return screen_region

    def update_pixmap(self, pixmap=None, *, crop: bool = True):
        if pixmap:
            self.monitor.setPixmap(pixmap)
            return

        if self.img is None:
            return

        if crop and self.coords:
            offsets = (
                self.x_offset.value(),
                self.y_offset.value(),
                self.x_offset.value(),
                self.y_offset.value(),
            )
            bbox = tuple(int(a+b) for a, b in zip(self.coords, offsets, strict=True))
            img = self.img.crop(bbox)
        else:
            img = self.img

        qimg = ImageQt(img)
        img_pixmap = QPixmap.fromImage(qimg)
        img_pixmap = img_pixmap.scaledToWidth(self.monitor.size().width(), mode=Qt.TransformationMode.SmoothTransformation)
        self.monitor.setPixmap(img_pixmap)

    @Slot(int)
    def update_pixmap_slot(self, value):
        self.update_pixmap(crop=True)


class ScalingCalibration(QWidget):

    def __init__(self):
        super().__init__()
        if settings.image.pixel_ratio is not None:
            self.pixel_ratio = settings.image.pixel_ratio
        else:
            self.pixel_ratio =  1

        self.aspect_ratio_inv = QGuiApplication.primaryScreen().size().height()/QGuiApplication.primaryScreen().size().width()

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
        self.scaling.setValue(self.pixel_ratio)

        self.scaling.valueChanged.connect(self.test_screenshot)

        self.monitor = QLabel()
        self.monitor.setFixedWidth(400)
        self.monitor.setFixedHeight(400*self.aspect_ratio_inv)
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

        # -------------------------------------------------------------------------------------
        # -------- Extra ----------------------------------------------------------------------
        # -------------------------------------------------------------------------------------

        self.threadpool = QThreadPool()
        self.screenshot_worker = ScreenshotWorker(self)
        self.screenshot_worker.signals.pixmap_update.connect(
            self.update_pixmap
        )
        self.threadpool.start(self.screenshot_worker)

    def get_screen_region(self):
        screen_region = QGuiApplication.primaryScreen().geometry().getCoords()
        screen_region = tuple(int(self.scaling.value()*a) for a in screen_region)
        return screen_region

    def update_pixmap(self, pixmap):
        pixmap = pixmap.scaledToWidth(self.monitor.size().width(), mode=Qt.TransformationMode.SmoothTransformation)
        self.monitor.setPixmap(pixmap)

    def test_screenshot(self):
        self.screenshot_worker = ScreenshotWorker(self)
        self.screenshot_worker.signals.pixmap_update.connect(
            self.update_pixmap
        )
        self.threadpool.start(self.screenshot_worker)


class CalibrationDialog(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Screen Region Calibration")
        self.setFixedSize(QSize(500, 500))

        self.scaling_widget = ScalingCalibration()
        self.offsets_widget = OffsetCalibration()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.close)

        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self.next)


        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_options)

        self.buttons_layout = QHBoxLayout()
        self.buttons_layout.addWidget(self.cancel_button)
        self.buttons_layout.addWidget(self.save_button)
        self.buttons_layout.addWidget(self.next_button)

        self.buttons = QWidget(self)
        self.buttons.setLayout(self.buttons_layout)

        # -------------------------------------------------------------------------------------
        # -------- Building Layout ------------------------------------------------------------
        # -------------------------------------------------------------------------------------


        self.stacked_layout = QStackedLayout()
        self.stacked_layout.addWidget(self.scaling_widget)
        self.stacked_layout.addWidget(self.offsets_widget)

        self.stacked_layout.setCurrentWidget(self.scaling_widget)

        self.main_layout = QVBoxLayout()
        self.main_layout.addLayout(self.stacked_layout)
        self.main_layout.addWidget(self.buttons)

        self.setLayout(self.main_layout)

    def save_options(self):
        settings.image.pixel_ratio = self.scaling_widget.scaling.value()
        settings.image.offsets["x"] = self.offsets_widget.x_offset.value()
        settings.image.offsets["y"] = self.offsets_widget.y_offset.value()
        self.close()

    def next(self):
        self.offsets_widget.pixel_ratio = self.scaling_widget.scaling.value()
        self.stacked_layout.setCurrentWidget(self.offsets_widget)
        self.next_button.hide()

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
