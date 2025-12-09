from PySide6.QtCore import (
    QObject,
    Signal,
)

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
