from PySide6.QtCore import (
    Qt,
    Signal,
    QThreadPool
)
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
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

from PIL import Image
from PIL.ImageQt import ImageQt

import util.screenshot as screenshot
from audio_bar import AudioBar

from player import Player_Worker, PlayerState


class Thumbnail(QLabel):

    clicked = Signal()

    def __init__(self, img_src, w, selectable=False):
        super().__init__()
        # self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.img_pixmap = None
        self.selectable = selectable
        self.selected = False
        self.hover = False
        self.width = w
        self.setImage(img_src, w)
        if selectable:
            self.enterEvent = self.enterEvent_override
            self.leaveEvent = self.leaveEvent_override

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
        self.clicked.emit()

    def enterEvent_override(self, event):
        # self.setCursor(Qt.PointingHandCursor)
        self.hover = True
        self.update()

    def leaveEvent_override(self, event):
        # self.setCursor(Qt.ArrowCursor)
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


class ConfirmationDialog(QDialog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selected_img_idx = 0

        self.setWindowTitle("Confirm")
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

        """
        Image Preview
        """

        self.img_top_label = QLabel("Image Preview")
        self.img_top_label.setFont(self.header_font)

        self.curr_img = Thumbnail(screenshot.images_tmp.deque[0].img_bytesIO, 400)

        self.thumbnails = []

        for i in range(6):
            tmp_thumb = Thumbnail(screenshot.images_tmp.deque[i].img_bytesIO, 100, selectable=True)
            tmp_thumb.clicked.connect(
                lambda i=i: self.select_img(i)
            )
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
        self.scroll_thumbs.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_thumbs.setMaximumHeight(self.curr_img.sizeHint().height())
        self.scroll_thumbs.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.scroll_thumbs.setWidget(self.scroll_content)

        self.thumbs_layout = QHBoxLayout()
        self.thumbs_layout.setSpacing(3)
        self.thumbs_layout.setAlignment(Qt.AlignHCenter)
        self.thumbs_layout.addWidget(self.curr_img)
        self.thumbs_layout.addWidget(self.scroll_thumbs)

        """
        Audio Preview
        """

        self.audio_top_label = QLabel("Audio Preview")
        self.audio_top_label.setFont(self.header_font)

        self.slider = QSlider()
        self.slider.setOrientation(Qt.Horizontal)

        self.play_button = QPushButton("Play")

        self.audio_bar = AudioBar(h=80, start_interval=10, end_interval=200)
        self.audio_bar.setPlayable(True)
        self.audio_bar.setPlayerCursor(40)

        self.threadpool = QThreadPool()
        self.player_state = PlayerState()
        self.player = None

        self.play_button.clicked.connect(self.playAudio)
        # self.player_state.signals.cursor_update.connect(
        #     self.update_cursor
        # )
        self.player_state.setCursor(self.audio_bar.left_handle)

        self.zoom_slider = QSlider()
        self.zoom_slider.setOrientation(Qt.Horizontal)
        self.zoom_slider.setMinimum(1)
        self.zoom_slider.setMaximum(32)
        self.zoom_slider.setFixedWidth(100)
        self.zoom_slider.valueChanged.connect(
            lambda val: self.audio_bar.setZoom(val)
        )

        self.scroll_audio = QScrollArea()
        self.scroll_audio.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_audio.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_audio.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # self.scroll_audio.setMaximumWidth(500)
        self.scroll_audio.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.scroll_audio.setWidget(self.audio_bar)
        self.scroll_audio.setStyleSheet("""
            QScrollArea{
                border: 1px solid #909090;
                border-radius:2px;
            }
        """)

        self.bottom_audio_layout = QHBoxLayout()
        self.bottom_audio_layout.setAlignment(Qt.AlignHCenter)
        self.bottom_audio_layout.addWidget(self.play_button, alignment=Qt.AlignLeft)
        self.bottom_audio_layout.addSpacerItem(QSpacerItem(50, 5, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed))
        self.bottom_audio_layout.addWidget(self.zoom_slider, alignment=Qt.AlignRight)
        self.bottom_audio_layout.setStretch(1, 1)

        """
        Sentence Preview
        """

        self.sentence_top_label = QLabel("Sentence Preview")
        self.sentence_top_label.setFont(self.header_font)

        self.sentence_font = QFont()
        self.sentence_font.setPointSize(20)

        self.sentence_text_edit = QTextEdit("日本人が肉を日常食べるようになったのは明治以降である. 日本人が肉を日常食べるようになったのは明治以降である.")
        self.sentence_text_edit.setFixedHeight(100)
        self.sentence_text_edit.setFont(self.sentence_font)

        """
        Build Layout
        """

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.img_top_label)
        self.layout.addLayout(self.thumbs_layout)
        self.layout.addSpacerItem(QSpacerItem(5, 10))
        self.layout.addWidget(self.audio_top_label)
        self.layout.addWidget(self.scroll_audio)
        self.layout.addLayout(self.bottom_audio_layout)
        self.layout.addSpacerItem(QSpacerItem(5, 10))
        self.layout.addWidget(self.sentence_top_label)
        self.layout.addWidget(self.sentence_text_edit)
        self.layout.addWidget(self.buttonBox)
        # self.layout.addWidget(self.scroll_audio)
        self.setLayout(self.layout)

    def select_img(self, i: int) -> None:
        self.thumbnails[self.selected_img_idx].setSelected(False)
        self.selected_img_idx = i
        self.thumbnails[self.selected_img_idx].setSelected(True)
        self.curr_img.setImage(screenshot.images_tmp.deque[i].img_bytesIO)

    def playAudio(self) -> None:
        if self.player_state.playing:
            self.play_button.setText("Play")
            self.player.stop()
        else:
            self.play_button.setText("Pause")
            self.player = Player_Worker(self.player_state)
            self.threadpool.start(self.player)

    def update_cursor(self, cursor: int) -> None:
        if cursor < self.audio_bar.left_handle:
            self.audio_bar.setPlayerCursor(cursor=self.audio_bar.left_handle)
        elif cursor > self.audio_bar.right_handle:
            self.player.stop()
            self.play_button.setText("Play")
            self.audio_bar.setPlayerCursor(cursor=self.audio_bar.right_handle)
        else:
            self.audio_bar.setPlayerCursor(cursor)
