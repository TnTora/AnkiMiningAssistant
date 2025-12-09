import sounddevice as sd
from threading import Thread, Event

from . import audio
from .shared_components import PlayerSignals, PlayerState
from util.database import settings

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import numpy as np
    from collections.abc import Sequence


class PlayerWorkerSD(Thread):
    """Worker thread."""

    blocksize = 83

    def __init__(self, player_state: PlayerState, audio_data: "Sequence[audio.AudioInterval] | None" = None) -> None:
        super().__init__()
        self.player_state = player_state
        self.buffer = audio.buffers["primary"]
        self.frozen_deque = audio_data
        self.stop_event = Event()
        self.block_iter = None
        self.current_block = None

    def stop(self) -> None:
        self.stop_event.set()

    def callback(self, outdata: "np.ndarray", frames: int, time, status: sd.CallbackFlags):
        try:
            if self.block_iter is None:
                self.block_iter = self.buffer.get_data_in_blocks(
                    len(outdata),
                    starting_idx=self.player_state.cursor,
                    audio_data=self.frozen_deque,
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

    def run(self) -> None:
        self.player_state.playing = True
        self.player_state.signals.playing_state_changed.emit(True)

        if self.player_state.cursor == self.player_state.total_intervals:
            self.player_state.setCursor(0)

        stream = sd.OutputStream(
            samplerate=settings.audio.samplerate, blocksize=0,
            device=sd.default.device, channels=self.buffer.channels,
            callback=self.callback, finished_callback=self.stop_event.set)
        with stream:
            self.stop_event.wait()

        self.player_state.playing = False
        self.player_state.signals.playing_state_changed.emit(False)
