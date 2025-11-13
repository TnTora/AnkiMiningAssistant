from threading import Event, Thread
import soundcard as sc
import sys

from PySide6.QtCore import (
    QObject,
    Signal,
)

from util import audio
from util.database import settings

platform = sys.platform


class PlayerSignals(QObject):

    cursor_update = Signal(int)
    playing_state_changed = Signal(bool)


class PlayerState:

    def __init__(self) -> None:
        self.total_intervals = 0
        self.cursor = 0
        self.playing = False
        self.signals = PlayerSignals()

    def setCursor(self, cursor: int) -> None:
        self.cursor = cursor
        self.signals.cursor_update.emit(self.cursor)

    def advanceCursor(self) -> None:
        self.cursor += 1
        self.signals.cursor_update.emit(self.cursor)


class Player_Worker(Thread):
    """Player Worker thread."""

    # on macOS, blocksize range might be limited
    blocksize = 1 << 14 if platform == "win32" else 1 << 8 # 256

    def __init__(self, player_state: PlayerState, audio_buffer: audio.AudioBuffer | None = None):
        super().__init__()
        self.player_state = player_state
        self.buffer = audio_buffer or audio.buffer
        self.stop_event = Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        self.player_state.playing = True
        self.player_state.signals.playing_state_changed.emit(True)

        if self.player_state.cursor == self.player_state.total_intervals:
            self.player_state.setCursor(0)

        with sc.default_speaker().player(samplerate=settings.audio.samplerate, blocksize=self.blocksize) as sp:

            for block, interval_idx in audio.AudioBuffer.get_data_in_blocks(
                    self.buffer,
                    self.blocksize,
                    starting_idx=self.player_state.cursor
            ):

                if self.stop_event.is_set() or not self.player_state.playing:
                    break

                sp.play(block)

                if interval_idx != self.player_state.cursor:
                    self.player_state.setCursor(interval_idx)

        self.player_state.playing = False
        self.player_state.signals.playing_state_changed.emit(False)
