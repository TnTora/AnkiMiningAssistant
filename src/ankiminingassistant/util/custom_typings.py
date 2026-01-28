from typing import Protocol, TypedDict, Literal


class AudioInputDevice(Protocol):
    name: str
    channels: int


class Session(TypedDict):
    AppName: str
    WindowTitle: str
    continuous_recording: bool
    auto_update: bool
    open_in_browser: bool
    preview_note: bool
    use_screen_region: bool
    screen_region: tuple[int, ...]

SessionKeys = Literal[
    "AppName",
    "WindowTitle",
    "continuous_recording",
    "auto_update",
    "open_in_browser",
    "preview_note",
    "use_screen_region",
    "screen_region",
]

SessionKeysBool = Literal[
    "continuous_recording",
    "auto_update",
    "open_in_browser",
    "preview_note",
    "use_screen_region",
]
