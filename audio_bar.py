import numpy as np

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QMouseEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
)

import util.audio as audio


def calculate_rms(a):
    return np.sqrt(np.mean(np.square(a), axis=0))


class AudioBar(QWidget):

    def __init__(self, h, start_interval=None, end_interval=None):
        super().__init__()
        # zoom from 1 to 32
        self.zoom: int = 1
        self.h = h
        self.w = 0
        self.total_intervals = len(audio.buffer)
        self.setFixedHeight(h)
        self.intervals_rms_vad = []
        self.peak = 0
        self.calculate_intervals()

        self.left_handle = start_interval
        self.right_handle = end_interval

        self.left_handle_x = 0
        self.right_handle_x = 0

        self.handle_pressed = None

        self.playable = False
        self.player_cursor = 0
        self.player_cursor_x = 0

    def calculate_intervals(self):
        self.intervals_rms_vad = []
        self.peak = 0
        tmp_interval = np.empty((0, audio.buffer.channels))
        tmp_vad = False
        i = 0
        for interval in audio.buffer:
            tmp_interval = np.append(tmp_interval, interval.data, axis=0)
            tmp_vad = tmp_vad or interval.vad > 0.5

            i += 1
            if i % self.zoom != 0:
                continue

            rms = np.max(calculate_rms(tmp_interval))
            self.intervals_rms_vad.append((rms, tmp_vad))

            if rms > self.peak:
                self.peak = rms

            tmp_interval = np.empty((0, audio.buffer.channels))
            tmp_vad = False
        if len(tmp_interval) > 0:
            rms = np.max(calculate_rms(tmp_interval))
            self.intervals_rms_vad.append((rms, tmp_vad))
        self.w = (len(self.intervals_rms_vad) * 5) + 2
        self.setFixedWidth(self.w)

    def setZoom(self, scale: int) -> None:
        self.zoom = scale
        # bar width 3px, space inbetween 2px
        self.w = (int(self.total_intervals/self.zoom) * 5) + 4
        self.setFixedSize(QSize(self.w, self.height()))
        self.calculate_intervals()
        self.update()

    def setPlayable(self, playable: bool) -> None:
        """Display player cursor"""
        self.playable = playable

    def setPlayerCursor(self, cursor: int) -> None:
        """Set cursor to a specific interval"""
        min_interval = self.left_handle or 0
        max_interval = self.right_handle or self.total_intervals

        if cursor < min_interval or cursor > max_interval:
            return

        self.player_cursor = cursor
        self.update()

    def getRange(self):
        return self.left_handle, self.right_handle+1

    # TODO: Control zoom via scrolling
    # TODO: change cursor when close to handles
    # TODO: add timeline

    def mousePressEvent(self, event: QMouseEvent):
        if self.left_handle is None:
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if abs(event.pos().x() - self.player_cursor_x) < 10:
            self.handle_pressed = "player"
        elif abs(event.pos().x() - self.left_handle_x) < 10:
            self.handle_pressed = "left"
        elif abs(event.pos().x() - self.right_handle_x) < 10:
            self.handle_pressed = "right"

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.handle_pressed = None

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.left_handle is None:
            return

        pos_x = event.pos().x()

        if self.handle_pressed == "left":

            if pos_x > self.right_handle_x - 6:
                self.left_handle = int((self.right_handle_x - 6 - 2)*self.zoom/5)
            else:
                # self.left_handle_x = 2+(self.left_handle)*5/self.zoom
                self.left_handle = max(int((pos_x - 2)*self.zoom/5), 0)

            self.update()

        elif self.handle_pressed == "right":

            if pos_x < self.left_handle_x + 6:
                self.right_handle = int((self.left_handle_x + 6 - 2)*self.zoom/5)
            else:
                self.right_handle = min(int((pos_x - 2)*self.zoom/5), self.total_intervals)

            self.update()

        elif self.handle_pressed == "player":

            min_interval = self.left_handle or 0
            max_interval = self.right_handle or self.total_intervals
            tmp_interval = int((pos_x + 6 - 2)*self.zoom/5)

            if tmp_interval < min_interval:
                self.player_cursor = min_interval
            elif tmp_interval > max_interval:
                self.player_cursor = max_interval
            else:
                self.player_cursor = tmp_interval

            self.update()

    def paintEvent(self, event):
        print(f"printevent: {event}, rect: {event.rect()}, region: {event.region()}")
        super().paintEvent(event)
        if QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark:
            background_color = QColor(100, 100, 100)
        else:
            background_color = QColor(245, 245, 245)

        painter = QPainter(self)
        pen = QPen()
        pen.setColor(background_color)
        painter.setPen(pen)
        brush = QBrush()
        brush.setColor(background_color)
        brush.setStyle(Qt.SolidPattern)
        painter.setBrush(brush)

        # Draw Background
        painter.drawRect(0, 0, painter.device().width(), painter.device().height())

        pen_voice = QPen()
        pen_voice.setColor(QColor(216, 191, 65))
        brush_voice = QBrush()
        brush_voice.setColor(QColor(216, 191, 65))
        brush_voice.setStyle(Qt.SolidPattern)

        no_voice_color = QColor(20, 20, 20)
        pen.setColor(no_voice_color)
        brush.setColor(no_voice_color)
        painter.setPen(pen)
        painter.setBrush(brush)
        bar_x_pos = 2

        # Draw bars
        for rms, vad in self.intervals_rms_vad:

            if vad:
                painter.setPen(pen_voice)
                painter.setBrush(brush_voice)
            else:
                painter.setPen(pen)
                painter.setBrush(brush)

            bar_heigth = (rms/self.peak) * (painter.device().height()-6)
            bar_y_pos = (painter.device().height() - bar_heigth)/2
            painter.drawRoundedRect(QRectF(bar_x_pos, bar_y_pos, 3, bar_heigth), 1, 3)
            bar_x_pos += 5

        # Draw Selection box
        if self.left_handle is not None and self.right_handle is not None:
            selection_color_pen = QColor(252, 115, 10)
            selection_color_brush = QColor(252, 115, 10, 127)
            pen.setColor(selection_color_pen)
            painter.setPen(pen)
            brush.setColor(selection_color_brush)
            painter.setBrush(brush)

            # print(f"self.right_handle, self.left_handle: {self.right_handle}, {self.left_handle}")
            selection_w = (3 + (self.right_handle - self.left_handle)*5)/self.zoom
            self.left_handle_x = 2+(self.left_handle)*5/self.zoom
            self.right_handle_x = self.left_handle_x + selection_w
            # print(f"self.right_handle_x, self.left_handle_x: {self.right_handle_x}, {self.left_handle_x}")
            painter.drawRect(self.left_handle_x, 0, selection_w, painter.device().height())

        # Draw Player Cursor
        if self.playable:
            player_cursor_color = QColor(237, 34, 16)
            pen.setColor(player_cursor_color)
            pen.setWidth(1)
            painter.setPen(pen)
            self.player_cursor_x = 2+(self.player_cursor)*5/self.zoom
            painter.drawLine(self.player_cursor_x, 0, self.player_cursor_x, painter.device().height())

        painter.end()
