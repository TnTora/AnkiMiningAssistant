import sys
from pathlib import Path
from os import getenv

platform = sys.platform
is_wayland = False

config_base = getenv("APPDATA") or getenv("XDG_CONFIG_HOME") or "~/.config"
config_path = Path(config_base).expanduser() / "AnkiMiningAssistant"
config_path.mkdir(parents=True, exist_ok=True)

if platform == "linux":

    is_wayland = (
        "wayland" in getenv("WAYLAND_DISPLAY", "").lower()
        or "wayland" in getenv("XDG_SESSION_TYPE", "").lower()
    )

    if is_wayland:
        from .wayland import *
    else:
        from .x11 import *

elif platform == "darwin":

    from .mac import *

elif platform == "win32":

    from .win import *

else:
    msg = f"AnkiMiningAssistant does not support {platform}"
    raise NotImplementedError(msg)
