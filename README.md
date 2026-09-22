

# AnkiMiningAssistant

The aim of this project is to develop a cross-platoform software to facilitate the creation of useful Anki cards while sentence mining by automatically (or manually) adding screenshots and sentence audio.

Both screenshots and audio recording are obtained using platform dependant native methods, meaning there is no need to install or setup third-party software, thus simplifying the setup process and reducing the total

> **NOTE**: This program is still in its early stages and has not been thoroughly tested, if you encounter any problem make sure to open an Issue. Apple Silicon mac and most linux distros heve never been tested.

## Demo

https://github.com/user-attachments/assets/454570c5-b7b6-4351-979c-d6014fb1e3f2

## Features

**Current**
- Native system audio monitoring
- Native window screenshots
- Select specific window for screenshots
- Select screen section for screenshots
- Support multiple sessions with different settings
- Automatically show Expression and Sentence of the last anki card added
- Use AnkiConnect to facilitate deck and note-type config
- Voice detection using silero-vad
    - Automatically pause monitoring after specified amount of silence and restart upon new lines received
    - Automatically identify end of sentence audio
- Option to preview card info before adding to Anki
    - Manually modify audio selection if necessary
    - Choose different screenshot
    - Modify Sentence field
- Switch between automatic and manual update of cards
- And more... (Check Usage and Configuration) 

**Planned**
- Compiled Binary/App Bundle
- Add custom tags to anki card
    - Modify which tags to include in the card preview window
- Better support for multi monitor setups
- Ability to update an older anki card instead of just the last one added
- More flexible note type fields handling

## Installation

As of right now, the app is only available as a python package. In the future binaries/App bundle will be made available.

To install the python package it is recommended to use `uv tool`:

- Install [uv](https://docs.astral.sh/uv/getting-started/installation/)
- If you are on linux you may need to install `libpipewire-0.3` and the `PortAudio` library.
- run the following command in terminal
```
uv tool install AnkiMiningAssistant --pyhton 3.12
```

After installing, you can use the following command to open the application
```
anki-mining-assistant
```
Opening the app for the first time will take a while, even if nothing seems to be happening let it run. Subsequent runs should open normally.

## Configuration

Here are the necessary settings for the program to work, for all other refer to the descriptions provided under each settings.

### General
Make sure the `WebSocket Port` selected does not conflict with any other software you are using. In most cases the default will work.

Add a custom websocket server to listen to in order to receive text from the media you are mining from. Already included as default are:
- localhost:6677 (default used by [mpv_websocket_subs](https://github.com/TnTora/mpv_websocket_subs) and [mpv_websocket](https://github.com/kuroahna/mpv_websocket))
- localhost:2333 (default used by [LunaTranslator](https://docs.lunatranslator.org/en/))

### Anki

Make sure [AnkiConnect](https://github.com/amikey/anki-connect) addon is installed on Anki.

Verify that `AnkiConnect PORT` matches the one in AnkiConnect settings. The default should work most of the time.

Once connection with Anki is established, `Media Directory` should be populated automatically.

Add your preferred `Note Types` by selecting them from the drop down menu and pressing the `+` button.

For each note type you added you need to select the matching fields
- `Expression`: word or expression learned in the card. Will be shown in main interface for the last note added
- `Sentence`: sentence being mined. Will be shown in main interface for the last note added
- `Sentence Audio`: audio recorder from this program will be added to this field
- `Picture`: screenshots from this program will be added to this field

### Audio

Should work with the default.

If you notice problems with the voice detection, try changing `Vad Threshold` between `0.1` and `0.9`.

A higher value will be stricter (too high might lead to some false negatives), while a lower will be laxer (too low might lead to some false positives).

### Image

Should work with the default.

If you notice problems with screenshots being cutoff or scaled wrong, try clicking the `Calibrate` button. This is especially necessary on linux under wayland because the program has no access to the window coordinates.


## Usage

## Dependencies

| Name | LICENSE |
|------|---------|
| [PySide6](https://wiki.qt.io/Qt_for_Python) | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only |
| [websockets](https://github.com/python-websockets/websockets) | BSD-3-Clause |
| [SoundCard](https://github.com/bastibe/SoundCard) | BSD 3-clause |
| [sounddevice](https://github.com/spatialaudio/python-sounddevice/) | MIT |
| [soundfile](https://github.com/bastibe/python-soundfile) | BSD 3-Clause License |
| [torch](https://github.com/pytorch/pytorch) | BSD-3-Clause  |
| [torchaudio](https://github.com/pytorch/audio) | BSD-2-Clause license  |
| [silero-vad](https://github.com/snakers4/silero-vad) | MIT License |
| [pillow](https://python-pillow.github.io/) | MIT-CMU |
| [numpy](https://github.com/numpy/numpy) | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0  |
| [cffi](https://github.com/python-cffi/cffi) | MIT |
| [pyobjc](https://github.com/ronaldoussoren/pyobjc) | MIT |
| [PyWinCtl](https://github.com/Kalmat/PyWinCtl) | BSD-3-Clause |
| [Xlib](https://github.com/python-xlib/python-xlib) | GNU Lesser General Public License v2 or later (LGPLv2+) (LGPLv2+) |
| [jeepney](https://gitlab.com/takluyver/jeepney) | MIT |
| [pywin32](https://github.com/mhammond/pywin32) | Python Software Foundation License (PSF)*<sup>[[1]](https://github.com/mhammond/pywin32/issues/1127#issuecomment-393364022)</sup> |
