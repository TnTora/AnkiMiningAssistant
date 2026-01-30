from setuptools import Extension, setup
import sys

if sys.platform == "linux":
    import subprocess
    pkg_config = subprocess.run(["pkg-config", "--cflags", "--libs", "libpipewire-0.3"], capture_output=True, check=True)

    output = (temp for temp in pkg_config.stdout.decode().split(" "))
    inc_dirs = []
    extra_args = ["-fPIC"]

    for opt in output:
        if opt.startswith("-I"):
            inc_dirs.append(opt[2:])
        elif opt.startswith("-"):
            extra_args.append(opt)

    setup(
        ext_modules=[
            Extension(
                name="pipewire_util",
                sources = ["lib/pipewire_util.c"],
                include_dirs = inc_dirs,
                extra_compile_args = extra_args,
                libraries = ["pipewire-0.3"]
            ),
        ]
    )
else:
    setup()
