from setuptools import Extension, setup
from os import getenv

is_wayland = (
    "wayland" in getenv("WAYLAND_DISPLAY", "").lower()
    or "wayland" in getenv("XDG_SESSION_TYPE", "").lower()
)

if is_wayland:
    setup(
        ext_modules=[
            Extension(
                name="pipewire_util",
                sources = ["lib/pipewire_util.c"],
                include_dirs = ["/usr/include/pipewire-0.3", "/usr/include/spa-0.2"],
                extra_compile_args = ["-fPIC", "-D_REENTRANT", "-lpipewire-0.3"],
                libraries = ["pipewire-0.3"]
            ),
        ]
    )
