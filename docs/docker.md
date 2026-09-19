# Docker

The published image runs the simulated devices and the control API with no Python on your machine:

```sh
docker run --rm \
  -p 127.0.0.1:9100:9100 \
  -p 127.0.0.1:8765:8765 \
  emupos/emupos:0.2.0
```

Your POS prints to `127.0.0.1:9100`. The control API is at `http://127.0.0.1:8765`.

## Publish to 127.0.0.1, not to every interface

The bundled configuration binds `0.0.0.0` inside the container, and `emupos run` prints a warning about it on every start:

> warning: the control API listens on 0.0.0.0 and has no authentication: any machine that can reach this address can control the devices

That warning is expected here and the configuration is not a mistake. Docker publishes ports to the container's `eth0`, never to its loopback, so emupos's usual `127.0.0.1` defaults would leave `-p` connecting to nothing at all. What decides who can reach you is the **publish** flag, not the bind address: `-p 127.0.0.1:8765:8765` keeps the API on your own machine. Writing `-p 8765:8765` instead would expose it to your network, and then the warning means exactly what it says.

## Your own configuration

`emupos run` reads `emupos.yaml` from its working directory, which is `/emupos`. Mount a file over the bundled one:

```sh
docker run --rm \
  -v ./emupos.yaml:/emupos/emupos.yaml:ro \
  -v ./receipts:/emupos/receipts \
  -p 127.0.0.1:9100:9100 -p 127.0.0.1:8765:8765 \
  emupos/emupos:0.2.0
```

Receipts are written under the working directory, so mount a volume there to keep them.

With docker compose:

```yaml
services:
  emupos:
    image: emupos/emupos:0.2.0
    ports:
      - "127.0.0.1:9100:9100"
      - "127.0.0.1:8765:8765"
    volumes:
      - ./emupos.yaml:/emupos/emupos.yaml:ro
      - ./receipts:/emupos/receipts
```

A POS in another service on the same network reaches the printer at `emupos:9100` and the API at `http://emupos:8765`, with no published ports at all.

## What the image contains, and why

Only devices whose wiring inside a container is the wiring of the real hardware:

| Device | Why it is faithful in a container |
|---|---|
| `front`, a printer on TCP 9100 | a network receipt printer genuinely is ESC/POS over a TCP socket |
| `lane1`, a keyboard-wedge scanner with `typed_by: client` | the keystrokes are pressed on your machine, by you, as a real scanner presses them |

### Keyboard scans are typed where you are

A container has no desktop, so it cannot type. `typed_by: client` means the simulator validates the scan, plans the keystrokes and publishes the delivery event, while `emupos scan` presses the keys on the machine with your POS window. That needs emupos installed there:

```sh
uv tool install emupos
emupos scan 6291041500213        # EMUPOS_API defaults to http://127.0.0.1:8765
```

See [macOS](macos-accessibility.md) and [Linux](linux-x11.md) for the permission each system asks for.

### Serial devices are not in the image

A scale, or a scanner in serial mode, needs a serial port. A pseudo-terminal created inside a container belongs to that container's own devpts, so the link your POS would open points at a device that does not exist on your machine — on macOS and Windows the container is inside Docker Desktop's Linux VM, one boundary further still.

The port has to exist where the POS can open it. For now, run emupos on the host for serial devices:

```sh
uv tool install emupos
emupos run --config scale.yaml
```

You can do that alongside the container: the printer keeps running in Docker, and the host emupos serves only the serial devices.

## The other commands

The CLI is in the image, so anything that does not type works without installing emupos:

```sh
docker exec <container> emupos devices
docker exec <container> emupos receipt show
```

`emupos scan` is the exception — run that on your own machine, for the reason above.
