import sys

platform = sys.platform
is_wayland = False

if platform == "linux":

    from os import getenv

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
