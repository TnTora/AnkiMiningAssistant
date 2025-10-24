import sys

__all__ = ["anki", "audio", "database", "screenshot","sockets" ]

from . import anki
from . import audio
from . import database
from . import screenshot
from . import sockets

if sys.platform == "linux":
    pass
elif sys.platform == "darwin":
    __all__ += ["AggregateDevice", "mac"]
    from . import AggregateDevice
    from . import mac
elif sys.platform == "win32":
    pass
else:
    msg = f"SoundCard does not support {sys.platform} yet"
    raise NotImplementedError(msg)
