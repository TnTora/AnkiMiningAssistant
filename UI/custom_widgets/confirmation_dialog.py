from collections.abc import Iterable
from PySide6.QtCore import (
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QListWidget,
    QScrollArea,
    QSpacerItem,
    QTextEdit,
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QDialog,
    QDialogButtonBox,
    QSlider,
    QSizePolicy,
)

import sys
from PIL import Image
from PIL.ImageQt import ImageQt

from .audio_bar import AudioBar

from util.screenshot import ImageStored
from util.audio import AudioBuffer

if sys.platform == "win32":
    from player_sd import PlayerState, Player_Worker
else:
    from player import PlayerState, Player_Worker


class AlertDialog(QDialog):

    def __init__(self, alert_txt, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setWindowTitle("Alert")

        QBtn = (
            QDialogButtonBox.Ok
        )

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)

        self.alert_label = QLabel(alert_txt)
        self.alert_label.setWordWrap(True)

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.alert_label, alignment=Qt.AlignHCenter)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)


class SelectLineDialog(QDialog):

    def __init__(self, found_lines):
        super().__init__()
        self.lines = found_lines

        self.setWindowTitle("Select Line")

        QBtn = (
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        self.main_label = QLabel("Select correct line: ")
        self.main_label.setWordWrap(True)

        self.line_list = QListWidget()
        self.line_list.setMinimumWidth(500)
        self.line_list.setWordWrap(True)
        self.list_font = QFont()
        self.list_font.setPointSize(20)
        self.line_list.setFont(self.list_font)
        self.line_list.setSpacing(5)
        self.line_list.addItems([f"{a["line"].time}: {a["line"].text}" for a in self.lines])

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.main_label)
        self.layout.addWidget(self.line_list)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)

    def selected_line(self):
        curr_idx = self.line_list.currentRow()
        if curr_idx > -1:
            return curr_idx


class Thumbnail(QLabel):

    clicked = Signal(int)

    def __init__(self, img_src, w, index=None, *, selectable=False):
        super().__init__()
        # self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.img_pixmap = None
        self.selectable = selectable
        self.selected = False
        self.hover = False
        self.width = w
        self.index = index
        self.setImage(img_src, w)
        if selectable and self.index is None:
            raise ValueError("missing or invalid index")

    def setImage(self, img_src, w=None):
        if w is not None:
            self.width = w

        with Image.open(img_src) as img:
            qimg = ImageQt(img)
            self.img_pixmap = QPixmap.fromImage(qimg).scaledToWidth(self.width, mode=Qt.TransformationMode.SmoothTransformation)

        self.setPixmap(self.img_pixmap)

    def setSelected(self, selected):
        self.selected = selected
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self.selectable:
            self.clicked.emit(self.index)

    def enterEvent(self, event):
        # self.setCursor(Qt.PointingHandCursor)
        if self.selectable:
            self.hover = True
            self.update()

    def leaveEvent(self, event):
        # self.setCursor(Qt.ArrowCursor)
        if self.selectable:
            self.hover = False
            self.update()

    def paintEvent(self, arg__1):
        super().paintEvent(arg__1)
        if not self.selectable:
            return
        if not self.hover and not self.selected:
            return
        painter = QPainter(self)
        pen = QPen()
        pen.setColor(QColor(86, 86, 86, 180))
        painter.setPen(pen)
        brush = QBrush()
        brush.setColor(QColor(22, 22, 22, 180))
        brush.setStyle(Qt.SolidPattern)
        painter.setBrush(brush)

        painter.drawRect(0, 0, self.size().width(), self.size().height())
        painter.end()


class NotePreviewDialog(QDialog):
    def __init__(  # noqa: PLR0915
        self,
        imgs: Iterable[ImageStored] | None = None,
        audio_data: AudioBuffer | None = None,
        audio_range: tuple[int, int] | None = None,
        sentence: str | None = None,
    ) -> None:

        super().__init__()
        self.imgs = imgs
        self.audio_data = audio_data
        self.audio_range = audio_range
        self.sentence = sentence
        self.selected_img_idx = 0

        self.setWindowTitle("Note Preview")
        # self.setMinimumWidth(600)
        self.setFocusPolicy(Qt.StrongFocus)

        QBtn = (
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        self.header_font = QFont()
        self.header_font.setPointSize(18)

        # --------------------------------------------------------------------------------------
        # ------------- Image Preview ----------------------------------------------------------
        # --------------------------------------------------------------------------------------

        if self.imgs:
            self.img_top_label = QLabel("Image Preview")
            self.img_top_label.setFont(self.header_font)

            self.curr_img = Thumbnail(self.imgs[0].img_bytesIO, 400)

            self.thumbnails = []

            for i in range(len(self.imgs)):
                tmp_thumb = Thumbnail(self.imgs[i].img_bytesIO, w=100, index=i, selectable=True)
                tmp_thumb.clicked.connect(self.select_img)
                self.thumbnails.append(tmp_thumb)

            self.thumbnails[0].setSelected(True)

            self.side_thumbs_layout = QVBoxLayout()
            self.side_thumbs_layout.setContentsMargins(3, 0, 0, 0)
            for thumb in self.thumbnails:
                self.side_thumbs_layout.addWidget(thumb)

            self.scroll_content = QWidget()
            self.scroll_content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.scroll_content.setLayout(self.side_thumbs_layout)

            self.scroll_thumbs = QScrollArea()
            self.scroll_thumbs.setFrameShape(QFrame.Shape.NoFrame)
            self.scroll_thumbs.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.scroll_thumbs.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
            self.scroll_thumbs.setViewportMargins(0, 0, 2, 0)
            self.scroll_thumbs.setMaximumHeight(self.curr_img.sizeHint().height())
            self.scroll_thumbs.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            self.scroll_thumbs.setWidget(self.scroll_content)

            self.thumbs_layout = QHBoxLayout()
            self.thumbs_layout.setSpacing(3)
            self.thumbs_layout.setAlignment(Qt.AlignHCenter)
            self.thumbs_layout.addWidget(self.curr_img)
            self.thumbs_layout.addWidget(self.scroll_thumbs)

        # --------------------------------------------------------------------------------------
        # ------------- Audio Preview ----------------------------------------------------------
        # --------------------------------------------------------------------------------------

        if self.audio_data:
            self.audio_top_label = QLabel("Audio Preview")
            self.audio_top_label.setFont(self.header_font)

            self.audio_bar = AudioBar(h=80, audio_data=audio_data, start_interval=audio_range[0], end_interval=audio_range[1], scroll_zoom=False)
            self.audio_bar.setPlayable(True)
            self.audio_bar.setPlayerCursor(40)
            self.audio_bar.player_cursor_updated.connect(
                self.update_bar_cursor
            )
            self.audio_bar.zoom_changed.connect(
                self.update_bar_zoom
            )

            self.zoom_slider = QSlider()
            self.zoom_slider.setOrientation(Qt.Horizontal)
            self.zoom_slider.setMinimum(1)
            self.zoom_slider.setMaximum(32)
            self.zoom_slider.setFixedWidth(100)
            self.zoom_slider.setValue(self.audio_bar.zoom)
            self.zoom_slider.valueChanged.connect(
                self.update_zoom
            )

            self.scroll_audio = QScrollArea()
            self.scroll_audio.setFrameShape(QFrame.Shape.NoFrame)
            self.scroll_audio.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
            self.scroll_audio.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            # self.scroll_audio.setMaximumWidth(500)
            self.scroll_audio.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
            self.scroll_audio.setWidget(self.audio_bar)
            self.scroll_audio.setStyleSheet("""
                QScrollArea{
                    border: 1px solid #909090;
                    border-radius:2px;
                }
            """)

            self.scroll_audio.ensureVisible(int(self.audio_bar.left_handle_x), 0, xmargin=self.scroll_audio.width()-100)

            self.player_state = PlayerState()
            self.player = Player_Worker(self.player_state, audio_buffer=self.audio_data)

            self.play_button = QPushButton("Play")
            self.play_button.clicked.connect(self.playAudio)
            self.player_state.signals.cursor_update.connect(
                self.update_cursor
            )
            self.player_state.setCursor(self.audio_bar.left_handle)

            self.reset_button = QPushButton("Reset Selection")
            self.reset_button.clicked.connect(self.reset_selection)

            self.zoom_label = QLabel("Zoom:")
            self.zoom_label.setAlignment(Qt.AlignVCenter)
            self.zoom_label.setContentsMargins(0, 0, 0, 4)
            # TODO: change label text to zoom icon

            self.bottom_audio_layout = QHBoxLayout()
            self.bottom_audio_layout.setAlignment(Qt.AlignHCenter)
            self.bottom_audio_layout.addWidget(self.play_button, alignment=Qt.AlignLeft)
            self.bottom_audio_layout.addWidget(self.reset_button, alignment=Qt.AlignLeft)
            self.bottom_audio_layout.addSpacerItem(QSpacerItem(50, 5, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed))
            self.bottom_audio_layout.addWidget(self.zoom_label, alignment=Qt.AlignRight)
            self.bottom_audio_layout.addWidget(self.zoom_slider, alignment=Qt.AlignRight)
            self.bottom_audio_layout.setStretch(1, 1)

        # --------------------------------------------------------------------------------------
        # ------------- Sentence Preview -------------------------------------------------------
        # --------------------------------------------------------------------------------------

        if self.sentence:
            self.sentence_top_label = QLabel("Sentence Preview")
            self.sentence_top_label.setFont(self.header_font)

            self.sentence_font = QFont()
            self.sentence_font.setPointSize(20)

            self.sentence_text_edit = QTextEdit()
            self.sentence_text_edit.setPlainText(self.sentence)
            self.sentence_text_edit.setFixedHeight(100)
            self.sentence_text_edit.setFont(self.sentence_font)

        # --------------------------------------------------------------------------------------
        # ------------- Build Layout ------------------------------------------------------------
        # --------------------------------------------------------------------------------------

        self.main_layout = QVBoxLayout()
        if self.imgs:
            self.main_layout.addWidget(self.img_top_label)
            self.main_layout.addLayout(self.thumbs_layout)
            self.main_layout.addSpacerItem(QSpacerItem(5, 20))
        if self.audio_data:
            self.main_layout.addWidget(self.audio_top_label)
            self.main_layout.addWidget(self.scroll_audio)
            self.main_layout.addLayout(self.bottom_audio_layout)
            self.main_layout.addSpacerItem(QSpacerItem(5, 20))
        if self.sentence:
            self.main_layout.addWidget(self.sentence_top_label)
            self.main_layout.addWidget(self.sentence_text_edit)
        self.main_layout.addWidget(self.buttonBox)
        self.setLayout(self.main_layout)

    def closeEvent(self, event):
        if self.audio:
            self.player.stop()

    @Slot(int)
    def select_img(self, i: int) -> None:
        self.thumbnails[self.selected_img_idx].setSelected(False)
        self.selected_img_idx = i
        self.thumbnails[self.selected_img_idx].setSelected(True)
        self.curr_img.setImage(self.imgs[i].img_bytesIO)

    def playAudio(self) -> None:
        if self.player_state.playing:
            self.play_button.setText("Play")
            self.player.stop()
        else:
            if self.audio_bar.player_cursor == self.audio_bar.right_handle:
                self.player_state.setCursor(self.audio_bar.left_handle)
                self.audio_bar.setPlayerCursor(self.audio_bar.left_handle)
            self.play_button.setText("Pause")
            self.player = Player_Worker(self.player_state, audio_data=self.audio_data)
            self.player.start()

    @Slot(int)
    def update_bar_cursor(self, cursor):
        self.player_state.setCursor(cursor)

    @Slot(int)
    def update_bar_zoom(self, zoom):
        self.zoom_slider.setValue(zoom)

    @Slot(int)
    def update_cursor(self, cursor: int) -> None:
        if cursor < self.audio_bar.left_handle:
            cursor = self.audio_bar.left_handle
            self.audio_bar.setPlayerCursor(cursor=self.audio_bar.left_handle)
        elif cursor >= self.audio_bar.right_handle:
            cursor = self.audio_bar.right_handle
            self.player.stop()
            self.play_button.setText("Play")
            self.audio_bar.setPlayerCursor(cursor=self.audio_bar.right_handle)
        else:
            self.audio_bar.setPlayerCursor(cursor)

        cursor_x = 2+(cursor)*5/self.audio_bar.zoom
        if self.player_state.playing:
            self.scroll_audio.ensureVisible(cursor_x, 0)

    @Slot(int)
    def update_zoom(self, value) -> None:
        self.audio_bar.setZoom(value)
        self.scroll_audio.ensureVisible(int(self.audio_bar.left_handle_x), 0, xmargin=self.scroll_audio.width()-100)

    @Slot()
    def reset_selection(self) -> None:
        self.audio_bar.setRange(*self.audio_range)
        self.scroll_audio.ensureVisible(int(self.audio_bar.left_handle_x)+200, 0)

    def getValues(self):
        tmp_img_idx = None
        tmp_interval = None
        tmp_sentence = None
        if self.imgs:
            tmp_img_idx = self.selected_img_idx
        if self.audio_data:
            tmp_interval = self.audio_bar.getRange()
        if self.sentence:
            tmp_sentence = self.sentence_text_edit.toPlainText().strip()
        return tmp_img_idx, tmp_interval, tmp_sentence
