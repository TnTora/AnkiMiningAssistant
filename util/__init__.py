import sys

__all__ = ["anki", "audio", "database", "platform_util", "screenshot", "sockets"]

from . import anki
from . import audio
from . import database
from . import screenshot
from . import sockets
from . import platform_util

if sys.platform == "linux":
    pass
elif sys.platform == "darwin":
    __all__ += ["AggregateDevice"]
    from . import AggregateDevice
elif sys.platform == "win32":
    pass
else:
    msg = f"No support for {sys.platform} yet"
    raise NotImplementedError(msg)
