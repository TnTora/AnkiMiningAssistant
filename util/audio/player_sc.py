from threading import Event, Thread
import soundcard as sc
import sys

from . import audio
from .shared_components import PlayerSignals, PlayerState
from util.database import settings

from collections.abc import Sequence

platform = sys.platform


class PlayerWorkerSC(Thread):
    """Player Worker thread."""

    # on macOS, blocksize range might be limited
    blocksize = 1 << 14 if platform == "win32" else 1 << 9 # 512

    def __init__(self, player_state: PlayerState, audio_data: Sequence[audio.AudioInterval] | None = None) -> None:
        super().__init__()
        self.player_state = player_state
        self.buffer = audio.buffers["primary"]
        self.audio_data = audio_data
        self.stop_event = Event()

    def stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        self.player_state.playing = True
        self.player_state.signals.playing_state_changed.emit(True)

        if self.player_state.cursor == self.player_state.total_intervals:
            self.player_state.setCursor(0)

        with sc.default_speaker().player(samplerate=settings.audio.samplerate, blocksize=self.blocksize) as sp:

            for block, interval_idx in self.buffer.get_data_in_blocks(
                    self.blocksize,
                    starting_idx=self.player_state.cursor,
                    audio_data=self.audio_data,
            ):

                if self.stop_event.is_set() or not self.player_state.playing:
                    break

                sp.play(block)

                if interval_idx != self.player_state.cursor:
                    self.player_state.setCursor(interval_idx)

        self.player_state.playing = False
        self.player_state.signals.playing_state_changed.emit(False)
