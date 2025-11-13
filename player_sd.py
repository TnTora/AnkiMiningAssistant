import sounddevice as sd
from threading import Thread, Event

from PySide6.QtCore import (
    QObject,
    Signal,
)

from util import audio
from util.database import settings


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
    """Worker thread."""

    blocksize = 83

    def __init__(self, player_state: PlayerState, audio_buffer: audio.AudioBuffer | None = None):
        super().__init__()
        self.player_state = player_state
        self.buffer = audio_buffer or audio.buffer
        self.stop_event = Event()
        self.block_iter = None
        self.current_block = None

    def stop(self):
        self.stop_event.set()

    def callback(self, outdata, frames, time, status):
        try:
            if self.block_iter is None:
                self.block_iter = audio.buffer.get_data_in_blocks(
                    self.buffer,
                    len(outdata),
                    starting_idx=self.player_state.cursor
                )
                self.current_block, interval_idx = next(self.block_iter)
            else:
                self.current_block, interval_idx = next(self.block_iter)
        except StopIteration as exc:
            raise sd.CallbackStop from exc
        if self.stop_event.is_set():
            raise sd.CallbackAbort
        if len(self.current_block) < len(outdata):
            outdata[:len(self.current_block)] = self.current_block
            outdata[len(self.current_block):].fill(0)
        else:
            outdata[:] = self.current_block
        if interval_idx != self.player_state.cursor:
            self.player_state.setCursor(interval_idx)

    def run(self):
        self.player_state.playing = True
        self.player_state.signals.playing_state_changed.emit(True)

        if self.player_state.cursor == self.player_state.total_intervals:
            self.player_state.setCursor(0)

        stream = sd.OutputStream(
            samplerate=settings.audio.samplerate, blocksize=0,
            device=sd.default.device, channels=audio.buffer.channels,
            callback=self.callback, finished_callback=self.stop_event.set)
        with stream:
            self.stop_event.wait()

        self.player_state.playing = False
        self.player_state.signals.playing_state_changed.emit(False)
