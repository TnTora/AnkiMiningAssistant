from PySide6.QtCore import (
    QSize,
    Qt,
    QRect,
    QPoint,
)
from PySide6.QtGui import QGuiApplication, QPainter, QColor, QPen, QBrush
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QSizePolicy,
)


class RegionSelect(QWidget):

    def __init__(self, x=None, y=None, w=None, h=None):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        screen_geometry = QGuiApplication.primaryScreen().geometry()
        self.setGeometry(screen_geometry)
        self.setFixedSize(screen_geometry.size())

        # use self.selection.normalized() when getting selection
        # to make sure the rect as positive width and height

        self.available_geometry = QGuiApplication.primaryScreen().availableGeometry()

        x = x or self.available_geometry.x()
        y = y or self.available_geometry.y()
        w = w or self.available_geometry.width()/2
        h = h or self.available_geometry.height()/2

        self.selection = QRect(x, y, w, h)

        self.pressed = ""
        self.old_mouse_pos = None

        self.lb = QLabel("Testing", parent=self)
        self.lb.setGeometry(50, 50, self.lb.width(), self.lb.height())

    def adjust_selection_box(self):
        """Keep the selection box within the available geometry."""
        curr_size = self.selection.size()
        new_top_left_x = max(self.available_geometry.left(), self.selection.left())
        new_top_left_x = min(new_top_left_x, self.available_geometry.right()-curr_size.width())
        new_top_left_y = max(self.available_geometry.top(), self.selection.top())
        new_top_left_y = min(new_top_left_y, self.available_geometry.bottom()-curr_size.height())
        new_top_left = QPoint(new_top_left_x, new_top_left_y)

        if new_top_left != self.selection.topLeft():
            self.selection.setTopLeft(new_top_left)
            self.selection.setSize(curr_size)


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

        func_points = {
            "topleft": self.selection.setTopLeft,
            "topright": self.selection.setTopRight,
            "bottomleft": self.selection.setBottomLeft,
            "bottomright": self.selection.setBottomRight,
        }

        if self.pressed in ["left", "right"]:
            func_edges[self.pressed](pos.x())
        elif self.pressed in ["top", "bottom"]:
            func_edges[self.pressed](pos.y())
        elif self.pressed != "center":
            func_points[self.pressed](pos)
        else:
            self.setCursor(Qt.BlankCursor)
            diff = pos - self.old_mouse_pos
            self.old_mouse_pos = pos
            self.selection.translate(diff)

        self.adjust_selection_box()
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        painter = QPainter()
        # painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.begin(self)
        painter.fillRect( 0, 0, self.width(), self.height(), QColor(0, 0, 0, 200))
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.setPen(QPen(QColor(255, 0, 0), 1))
        painter.setBrush(QBrush(QColor(0, 0, 0, 100)))
        painter.drawRect(self.selection)
        painter.end()

