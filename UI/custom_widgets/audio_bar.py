from math import ceil, floor
import numpy as np
from collections.abc import Sequence
from itertools import islice

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
)

from util import audio
from util.database import settings

from time import perf_counter


def calculate_rms(a):
    return np.sqrt(np.mean(np.square(a), axis=0))


class AudioBar(QWidget):

    player_cursor_updated = Signal(int)
    zoom_changed = Signal(int)

    def __init__(
        self,
        h: int,
        audio_data: Sequence[audio.AudioInterval],
        start_interval: int,
        end_interval: int,
    ) -> None:

        super().__init__()
        # zoom from 1 to 32
        self.zoom: int = 3

        self.main_unit = 1
        self.sub_unit = 0.1
        one_sec_interval_px = 5/(settings.audio.interval_duration*self.zoom)
        self.sub_unit_px = round(self.sub_unit * one_sec_interval_px)
        self.main_unit_px = round(self.main_unit/self.sub_unit) * self.sub_unit_px

        self.audio_data = audio_data
        self.total_intervals: int = len(self.audio_data)
        self.zoomed_out_intervals: int = ceil(self.total_intervals/self.zoom)
        w: int = (self.zoomed_out_intervals * 5) + 2
        self.setFixedWidth(w)
        self.setFixedHeight(h)

        print(f"{self.zoomed_out_intervals = }")
        self.intervals_rms_vad = np.empty((self.zoomed_out_intervals, 2))
        self.intervals_rms_vad.fill(None)

        self.calculate_intervals()
        self.peak = np.max(self.intervals_rms_vad[:,0])

        self.left_handle: int = start_interval
        self.right_handle: int = end_interval

        self.left_handle_x: int | float = 2+(self.left_handle)*5/self.zoom
        self.right_handle_x: int | float = 5+(self.right_handle)*5/self.zoom
        self.handle_pressed = None

        self.playable = False
        self.player_cursor = -1
        self.player_cursor_x = 0

        self.old_mouse_pos_x = None

    def calculate_intervals(self, start_idx: int | None = None, end_idx: int | None = None) -> None:
        """
        Calculate intervals to draw.

        Merge audio intervals based on zoom attribute and calculate
        their respective rms.
        """
        start_idx: int = (start_idx or 0) * self.zoom
        end_idx: int = end_idx*self.zoom if end_idx is not None else self.total_intervals
        tmp_interval = np.empty((0, audio.buffers["primary"].channels))
        tmp_vad = False
        i: int = start_idx
        for interval in islice(self.audio_data, start_idx, end_idx):
            if not np.isnan(self.intervals_rms_vad[floor(i/self.zoom)][0]):
                i += 1
                continue

            tmp_interval = np.append(tmp_interval, interval.data, axis=0)
            tmp_vad = tmp_vad or interval.vad > settings.audio.vad_threshold

            i += 1
            if i % self.zoom != 0:
                continue

            rms = np.max(calculate_rms(tmp_interval))
            self.intervals_rms_vad[floor((i-1)/self.zoom)] = [rms, tmp_vad]

            tmp_interval = np.empty((0, audio.buffers["primary"].channels))
            tmp_vad = False
        if len(tmp_interval) > 0:
            rms = np.max(calculate_rms(tmp_interval))
            self.intervals_rms_vad[-1] = [rms, tmp_vad]

    def setZoom(self, scale: int) -> None:
        """Update zoom and attributes depending on its value."""
        if self.zoom == scale:
            return
        self.zoom = scale
        self.zoomed_out_intervals: int = ceil(self.total_intervals/self.zoom)
        self.intervals_rms_vad = np.empty((self.zoomed_out_intervals, 2))
        self.intervals_rms_vad.fill(None)
        w = (self.zoomed_out_intervals * 5) + 2
        self.setFixedWidth(w)
        self.update_units()
        self.update()

    def setPlayable(self, playable: bool) -> None:  # noqa: FBT001
        """Display player cursor."""
        self.playable = playable
        self.player_cursor = max(self.player_cursor, 0) if playable else -1
        self.player_cursor_x = max(self.player_cursor_x, 0) if playable else -10
        self.update()

    def setPlayerCursor(self, cursor: int) -> None:
        """Set cursor to a specific interval."""
        min_interval = self.left_handle or 0
        max_interval = self.right_handle or self.total_intervals

        if cursor < min_interval or cursor > max_interval:
            return

        self.player_cursor = cursor
        self.update()

    def setRange(self, start: int, end: int) -> None:
        """Set values for left_handle and right_handle delimiting selection."""
        self.left_handle = start
        self.right_handle = end
        self.left_handle_x = 2+(self.left_handle)*5/self.zoom
        self.right_handle_x = 5+(self.right_handle)*5/self.zoom

        if self.playable:
            self.player_cursor = start
            self.player_cursor_updated.emit(self.player_cursor)

        self.update()

    def getRange(self) -> tuple[int, int]:
        return self.left_handle, self.right_handle+1

    # TODO: change cursor when close to handles

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.left_handle is None:
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos_x = event.pos().x()
        if abs(pos_x - self.player_cursor_x) < 5:  # noqa: PLR2004
            self.handle_pressed = "player"
        elif abs(pos_x - self.left_handle_x) < 10:  # noqa: PLR2004
            self.handle_pressed = "left"
        elif abs(pos_x - self.right_handle_x) < 10:  # noqa: PLR2004
            self.handle_pressed = "right"
        elif self.left_handle_x < pos_x < self.right_handle_x:
            self.handle_pressed = "selection"
            self.old_mouse_pos_x = pos_x

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self.handle_pressed in ["player", "selection"] and self.playable:
            self.player_cursor_updated.emit(self.player_cursor)
        self.handle_pressed = None
        self.old_mouse_pos_x = None

    def move_left_handle(self, new_pos: float) -> None:
        if new_pos > self.right_handle_x - 6:
            self.left_handle = int((self.right_handle_x - 6 - 2)*self.zoom/5)
        else:
            # self.left_handle_x = 2+(self.left_handle)*5/self.zoom
            self.left_handle = max(int((new_pos - 2)*self.zoom/5), 0)

        if new_pos > self.player_cursor_x and self.playable:
            self.player_cursor = self.left_handle

        self.update()

    def move_right_handle(self, new_pos: float) -> None:
        if new_pos < self.left_handle_x + 6:
            self.right_handle = int((self.left_handle_x + 6 - 2)*self.zoom/5)
        else:
            self.right_handle = min(int((new_pos - 2)*self.zoom/5), self.total_intervals)

        if new_pos < self.player_cursor_x and self.playable:
            self.player_cursor = self.right_handle

        self.update()

    def move_player_cursor(self, new_pos: float) -> None:
        min_interval = self.left_handle or 0
        max_interval = self.right_handle or self.total_intervals
        tmp_interval = int((new_pos + 6 - 2)*self.zoom/5)

        if tmp_interval < min_interval:
            self.player_cursor = min_interval
        elif tmp_interval > max_interval:
            self.player_cursor = max_interval
        else:
            self.player_cursor = tmp_interval

        self.update()

    def move_selection_box(self, new_pos: float) -> None:
        if self.old_mouse_pos_x is None:
            return

        diff_x = new_pos - self.old_mouse_pos_x
        diff = round(diff_x*self.zoom/5)
        self.old_mouse_pos_x = new_pos

        if self.left_handle+diff < 0:
            diff = -self.left_handle
        elif self.right_handle+diff > self.total_intervals:
            diff = self.total_intervals - self.right_handle

        self.left_handle += diff
        self.right_handle += diff
        if self.playable:
            self.player_cursor += diff
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.left_handle is None:
            return

        pos_x = event.pos().x()

        if self.handle_pressed == "left":
            self.move_left_handle(pos_x)
        elif self.handle_pressed == "right":
            self.move_right_handle(pos_x)
        elif self.handle_pressed == "player":
            self.move_player_cursor(pos_x)
        elif self.handle_pressed == "selection":
            self.move_selection_box(pos_x)

    def to_seconds(self, pixels: float) -> float:
        return (pixels-2)/5*settings.audio.interval_duration*self.zoom

    def update_units(self) -> None:
        if self.zoom < 5:  # noqa: PLR2004
            self.main_unit = 1
            self.sub_unit = 0.1
        elif self.zoom < 10:  # noqa: PLR2004
            self.main_unit = 2
            self.sub_unit = 0.4
        elif self.zoom < 25:  # noqa: PLR2004
            self.main_unit = 2
            self.sub_unit = 1
        else:
            self.main_unit = 5
            self.sub_unit = 2.5

        one_sec_interval_px = 5/(settings.audio.interval_duration*self.zoom)
        self.sub_unit_px = round(self.sub_unit * one_sec_interval_px)
        self.main_unit_px = round(self.main_unit/self.sub_unit) * self.sub_unit_px

    def draw_bars(self, painter: QPainter, start_idx: int, end_idx: int) -> None:
        self.calculate_intervals(start_idx, end_idx)
        voice_color = QColor(216, 191, 65)
        no_voice_color = QColor(20, 20, 20)

        pen = QPen()
        pen.setColor(no_voice_color)

        brush = QBrush()
        brush.setColor(no_voice_color)
        brush.setStyle(Qt.BrushStyle.SolidPattern)

        pen_voice = QPen()
        pen_voice.setColor(voice_color)

        brush_voice = QBrush()
        brush_voice.setColor(voice_color)
        brush_voice.setStyle(Qt.BrushStyle.SolidPattern)

        bar_x_pos = 2 + start_idx*5

        for i in range(start_idx, end_idx):
            rms, vad = self.intervals_rms_vad[i]

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

    def draw_selection_box(self, painter: QPainter) -> None:
        selection_color_pen = QColor(252, 115, 10)
        selection_color_brush = QColor(252, 115, 10, 127)

        pen = QPen()
        brush = QBrush()
        brush.setStyle(Qt.BrushStyle.SolidPattern)

        pen.setColor(selection_color_pen)
        painter.setPen(pen)
        brush.setColor(selection_color_brush)
        painter.setBrush(brush)

        selection_w = (3 + (self.right_handle - self.left_handle)*5)/self.zoom
        self.left_handle_x = 2+(self.left_handle)*5/self.zoom
        self.right_handle_x = self.left_handle_x + selection_w
        painter.drawRect(QRectF(self.left_handle_x, 0, selection_w, painter.device().height()))

        handles_font = QFont()
        handles_font.setPixelSize(10)
        fm = QFontMetrics(handles_font)
        painter.setFont(handles_font)
        pen.setColor(QColor(0, 0, 0))
        painter.setPen(pen)

        # Draw left timestamp
        left_to_sec = self.to_seconds(self.left_handle_x)
        left_to_sec = (self.total_intervals * settings.audio.interval_duration) - left_to_sec
        left_msec = round((left_to_sec % 1)*1000)
        left_min, left_sec = divmod(left_to_sec, 60)
        left_time_str = f"-{int(left_min):02d}:{int(left_sec):02d}.{left_msec:03d} "
        left_txt_rect = fm.boundingRect(left_time_str).translated(int(self.left_handle_x), 0)

        # Move left timestamp if too close to right handle
        if selection_w < 2*(left_txt_rect.width()+5):
            left_txt_rect.translate(3, painter.device().height()-left_txt_rect.height()-2)
        else:
            left_txt_rect.translate(3, painter.device().height()-1)

        painter.drawText(left_txt_rect, left_time_str)

        # Draw rigth timestamp
        right_to_sec = self.to_seconds(self.right_handle_x)
        right_to_sec = (self.total_intervals * settings.audio.interval_duration) - right_to_sec
        right_msec = round((right_to_sec % 1)*1000)
        right_min, right_sec = divmod(right_to_sec, 60)
        right_time_str = f"-{int(right_min):02d}:{int(right_sec):02d}.{right_msec:03d} "
        right_txt_rect = fm.boundingRect(right_time_str).translated(int(self.right_handle_x), 0)
        right_txt_rect.translate(-right_txt_rect.width()-3, painter.device().height()-1)
        painter.drawText(right_txt_rect, right_time_str)

    def draw_timeline(self, painter: QPainter, start_px: int, end_px: int) -> None:
        pen = QPen()
        pen.setColor(QColor(30, 30, 30))
        painter.setPen(pen)

        current_px = start_px

        while current_px < end_px:
            if abs((current_px-2) % self.main_unit_px) < 0.01:  # noqa: PLR2004
                painter.drawLine(QPointF(current_px, 0), QPointF(current_px, 10))
            else:
                painter.drawLine(QPointF(current_px, 0), QPointF(current_px, 5))
            current_px += self.sub_unit_px


    def paintEvent(self, event: QPaintEvent) -> None:
        # super().paintEvent(event)

        start_idx = max(((event.rect().x()-2)//5)-10, 0)
        end_idx = ((event.rect().x()+event.rect().width()-2)//5)+10
        end_idx = min(end_idx, self.zoomed_out_intervals)

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
        brush.setStyle(Qt.BrushStyle.SolidPattern)
        painter.setBrush(brush)

        # Draw Background
        # painter.drawRect(0, 0, painter.device().width(), painter.device().height())
        painter.drawRect(event.rect())

        # Draw audio intervals as bars
        self.draw_bars(painter, start_idx, end_idx)

        # Draw Selection box
        if self.left_handle is not None and self.right_handle is not None:
            self.draw_selection_box(painter)

        # Draw Player Cursor
        if self.playable:
            player_cursor_color = QColor(237, 34, 16)
            pen.setColor(player_cursor_color)
            pen.setWidth(1)
            painter.setPen(pen)
            self.player_cursor_x = 3+(self.player_cursor)*5/self.zoom
            painter.drawLine(QPointF(self.player_cursor_x, 0), QPointF(self.player_cursor_x, painter.device().height()))

        # Draw timeline
        start_px = floor((event.rect().x()-2)/self.sub_unit_px) * self.sub_unit_px + 2 - 5*self.sub_unit_px
        start_px = max(2, floor(start_px))
        end_px = event.rect().x()+event.rect().width()-2
        self.draw_timeline(painter, start_px, end_px)

        painter.end()
