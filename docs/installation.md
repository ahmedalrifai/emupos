# Installation

emupos needs Python 3.13 or newer. [uv](https://docs.astral.sh/uv/) downloads a suitable Python for you, so it is the easiest way:

```sh
uv tool install emupos        # recommended
```

Other ways:

```sh
uvx emupos run --demo         # run without installing
pipx install emupos
pip install emupos            # for example inside a CI virtual environment
```

Check the installation:

```sh
emupos --version
```

## With Docker

The published image needs no Python on your machine:

```sh
docker run --rm -p 127.0.0.1:9100:9100 -p 127.0.0.1:8765:8765 emupos/emupos:latest
```

The image carries the receipt printer and a keyboard-wedge scanner; serial devices and the keystrokes themselves belong on your own machine. Ports, your own configuration and what a container cannot reach are covered in [docker.md](docker.md).

## From a clone

To run emupos from the source, for example to change it:

```sh
git clone https://github.com/ahmedalrifai/emupos.git
cd emupos
uv run emupos run --demo
```

## Next

- [quickstart.md](quickstart.md) prints a receipt, reads it and runs the printer out of paper, in about five minutes.
- Keyboard-mode scanning needs one setup step per operating system: [macos-accessibility.md](macos-accessibility.md), [linux-x11.md](linux-x11.md), [windows-keyboard.md](windows-keyboard.md).
- Serial devices on Windows need an existing COM port pair: [windows-serial.md](windows-serial.md).
