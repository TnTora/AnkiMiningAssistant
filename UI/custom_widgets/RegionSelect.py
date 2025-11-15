from PySide6.QtCore import (
    QSize,
    Qt,
    QRect,
    QPoint,
    Signal,
)
from PySide6.QtGui import QGuiApplication, QPainter, QColor, QPen, QBrush
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QHBoxLayout,
    QSizePolicy,
    QPushButton,
)

import sys
from util.database import sessionsdb


class RegionSelect(QWidget):
    cancelled = Signal()

    def __init__(self, x=None, y=None, w=None, h=None):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        screen_geometry = QGuiApplication.primaryScreen().geometry()
        self.pixel_ratio = QGuiApplication.primaryScreen().devicePixelRatio()
        self.setGeometry(screen_geometry)
        self.setFixedSize(screen_geometry.size())

        self.available_geometry = QGuiApplication.primaryScreen().availableGeometry()
        print(f"{screen_geometry = }\n{self.available_geometry = }")

        x = x or self.available_geometry.x()
        y = y or self.available_geometry.y()
        w = w or self.available_geometry.width()/2
        h = h or self.available_geometry.height()/2

        self.selection  = QRect(x, y, w, h)

        self.pressed = ""
        self.old_mouse_pos = None

        self.reset_button = QPushButton("Reset")
        self.reset_button.clicked.connect(
            lambda: self.reset_selection(x, y, w, h)
        )

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel)

        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_selection)

        self.buttons_layout = QHBoxLayout()
        self.buttons_layout.addWidget(self.reset_button)
        self.buttons_layout.addWidget(self.cancel_button)
        self.buttons_layout.addWidget(self.save_button)

        self.buttons = QWidget(self)
        self.buttons.setLayout(self.buttons_layout)

        self.adjust_selection_box()

    def cancel(self):
        self.cancelled.emit()
        self.close()

    def reset_selection(self, x, y, w, h):
        """Return selection to its initial position."""
        self.selection.setRect(x, y, w, h)
        self.buttons.setGeometry(
            self.selection.right()-self.buttons_layout.sizeHint().width(),
            self.selection.bottom(),
            self.buttons_layout.sizeHint().width(),
            self.buttons_layout.sizeHint().height(),
        )
        self.update()

    def save_selection(self):
        # use self.selection.normalized() when getting selection
        # to make sure the rect as positive width and height
        coords = self.selection.normalized().getCoords()
        if sys.platform != "darwin":
            coords = tuple(int(a*self.pixel_ratio) for a in coords)
        print(f"{self.pixel_ratio = }; {coords = }")
        sessionsdb.current_session["screen_region"] = coords
        self.close()

    def adjust_selection_box(self):
        """
        Keep the selection box within the available geometry.

        Limit minum selection size and calculate buttons position.
        """
        # curr_size = self.selection.size()
        curr_size = QSize(
            max(30, self.selection.size().width()),
            max(30, self.selection.size().height()),
        )
        new_top_left_x = max(self.available_geometry.left(), self.selection.left())
        new_top_left_x = min(new_top_left_x, self.available_geometry.right()-curr_size.width())
        new_top_left_y = max(self.available_geometry.top(), self.selection.top())
        new_top_left_y = min(new_top_left_y, self.available_geometry.bottom()-curr_size.height())
        new_top_left = QPoint(new_top_left_x, new_top_left_y)

        if new_top_left != self.selection.topLeft():
            self.selection.setTopLeft(new_top_left)
            self.selection.setSize(curr_size)

        if "left" in self.pressed or "top" in self.pressed:
            new_top_left = QPoint(
                max(0, min(new_top_left_x, self.selection.right()-30)),
                max(0, min(new_top_left_y, self.selection.bottom()-30)),
            )
            self.selection.setTopLeft(new_top_left)
        elif "right" in self.pressed or "bottom" in self.pressed:
            self.selection.setSize(curr_size)

        self.selection = self.selection.normalized()

        if self.available_geometry.bottom()-self.selection.bottom() > self.buttons_layout.sizeHint().height():
            buttons_y = self.selection.bottom()
        elif self.selection.top() - self.available_geometry.top() > self.buttons_layout.sizeHint().height():
            buttons_y = self.selection.top()-self.buttons_layout.sizeHint().height()
        else:
            buttons_y = self.selection.bottom()-self.buttons_layout.sizeHint().height()

        if self.selection.right()-self.available_geometry.left() < self.buttons_layout.sizeHint().width():
            button_x = 0
        else:
            button_x = self.selection.right()-self.buttons_layout.sizeHint().width()

        self.buttons.setGeometry(
            button_x,
            buttons_y,
            self.buttons_layout.sizeHint().width(),
            self.buttons_layout.sizeHint().height(),
        )

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        precision_in = 3
        precision_out = 5
        edges = {
            "top": QRect(self.selection.topLeft()-QPoint(precision_out, precision_out), QSize(self.selection.width()+2*precision_out, precision_in+precision_out)),
            "bottom": QRect(self.selection.bottomLeft()-QPoint(precision_out, precision_in), QSize(self.selection.width()+2*precision_out, precision_in+precision_out)),
            "left": QRect(self.selection.topLeft()-QPoint(precision_out, precision_out), QSize(precision_in+precision_out, self.selection.height()+2*precision_out)),
            "right": QRect(self.selection.topRight()-QPoint(precision_in, precision_out), QSize(precision_in+precision_out, self.selection.height()+2*precision_out)),
        }
        pos = event.pos()
        for edge, rect in edges.items():
            if rect.contains(pos):
                self.pressed += edge
        if self.selection.contains(pos, proper=True):
            self.pressed = self.pressed or "center"
            self.old_mouse_pos = pos

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.pressed = ""
        self.old_mouse_pos = None
        self.setCursor(Qt.ArrowCursor)

    def mouseMoveEvent(self, event):
        pos = event.pos()

        if not self.available_geometry.contains(pos):
            return
        if not self.pressed:
            return

        func_edges = {
            "top": self.selection.setTop,
            "bottom": self.selection.setBottom,
            "left": self.selection.setLeft,
            "right": self.selection.setRight,
        }

        func_corners = {
            "topleft": self.selection.setTopLeft,
            "topright": self.selection.setTopRight,
            "bottomleft": self.selection.setBottomLeft,
            "bottomright": self.selection.setBottomRight,
        }

        if self.pressed in ["left", "right"]:
            func_edges[self.pressed](pos.x())
        elif self.pressed in ["top", "bottom"]:
            func_edges[self.pressed](pos.y())
        elif self.pressed in func_corners:
            func_corners[self.pressed](pos)
        elif self.pressed == "center":
            self.setCursor(Qt.BlankCursor)
            diff = pos - self.old_mouse_pos
            self.old_mouse_pos = pos
            self.selection.translate(diff)

        self.adjust_selection_box()
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        painter = QPainter()
        painter.begin(self)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect( 0, 0, self.width(), self.height(), QColor(0, 0, 0, 200))
        painter.setPen(QPen(QColor(255, 0, 0), 1))
        painter.setBrush(QBrush(QColor(0, 0, 0, 100)))
        painter.drawRect(self.selection)
        # painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.end()

