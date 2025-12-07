from typing import Protocol


class AudioInputDevice(Protocol):
    name: str
    channels: int
