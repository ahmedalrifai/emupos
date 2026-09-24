# Quickstart

This takes about five minutes and works on every operating system; the scale and scan steps need macOS or Linux. Use two terminals.

If emupos is not installed yet, see [installation.md](installation.md).

## 1. Start the demo devices

In the first terminal:

```sh
emupos run --demo
```

```
emupos <version> · built-in demo configuration
DEVICE  TYPE     PROFILE          CONNECTIONS
front   printer  epson-tm-t20iii  tcp 127.0.0.1:9100
lane1   scanner  keyboard mode    types into the focused window
deli    scale    toledo8217-15kg  serial $TMPDIR/emupos/deli -> /dev/ttys009
control API http://127.0.0.1:8765
Running the demo configuration. Write your own with `emupos config init`.
Showing events as they happen. Press Ctrl+C to stop.
```

The demo has a printer `front` on TCP port 9100, a keyboard scanner `lane1` and, on macOS and Linux, a scale `deli` on a serial port. Leave it running: events appear here as they happen.

## 2. Look at the devices

In the second terminal:

```sh
emupos devices
```

```
DEVICE  TYPE     PROFILE          CONNECTIONS                                 STATE
front   printer  epson-tm-t20iii  tcp 127.0.0.1:9100                          drawer closed, faults: none
lane1   scanner  -                -                                           keyboard mode, suffix enter, 10 ms between keys
deli    scale    toledo8217-15kg  serial $TMPDIR/emupos/deli -> /dev/ttys009  0.000 kg stable
```

## 3. Print a receipt, as your POS would

Send ESC/POS bytes to port 9100: initialise (`ESC @`), a line of text, and a cut (`GS V 0`).

macOS and Linux:

```sh
printf '\x1b\x40Hello from emupos\n\x1d\x56\x00' | nc -w 1 127.0.0.1 9100
```

Any operating system, with uv:

```sh
uv run --no-project python -c "import socket; s = socket.create_connection(('127.0.0.1', 9100)); s.sendall(b'\x1b@Hello from emupos\n\x1dV\x00'); s.close()"
```

The first terminal shows the receipt being completed:

```
00:26:32.881  front  printer.job.completed         job 1 · cut → front-20260913T222632880Z-a04808eb
```

## 4. Read the receipt

```sh
emupos receipt show
```

```
Hello from emupos
```

`emupos receipt show --save receipt.png` also writes the rendered image. Receipts are kept in `./receipts`.

## 5. Run out of paper

```sh
emupos fault set front paper-out
```

Now ask the printer for its paper status (`DLE EOT 4`), as a POS does:

```sh
printf '\x10\x04\x04' | nc -w 1 127.0.0.1 9100 | od -An -tx1
```

```
7e
```

`7e` means "paper not present". Any operating system:

```sh
uv run --no-project python -c "import socket; s = socket.create_connection(('127.0.0.1', 9100)); s.sendall(b'\x10\x04\x04'); print(s.recv(1).hex())"
```

Print another receipt now (step 3 with different text): it is held, like on a real printer without paper. Put a new roll in and it prints:

```sh
emupos fault clear front paper-out
emupos receipt show
```

All status bytes are listed in [protocols/escpos-status.md](protocols/escpos-status.md).

## 6. Weigh something (macOS and Linux)

```sh
emupos scale set 1.25kg
```

Ask the scale for the weight over its serial port (`W`), as a POS does, here with pyserial:

```sh
uv run --no-project --with pyserial python -c "import serial; s = serial.Serial('${TMPDIR:-/tmp}/emupos/deli', 9600, bytesize=7, parity='E', timeout=1); s.write(b'W'); print(s.read_until(b'\r'))"
```

```
b'\x0201.250\r'
```

The protocol is described in [protocols/toledo8217.md](protocols/toledo8217.md). A scale using the `sma-15kg` profile speaks the SMA protocol instead: [protocols/sma.md](protocols/sma.md).

## 7. Scan a barcode (optional)

```sh
emupos scan 5901234123457
```

During the 3-second countdown, click the window that should receive the scan: emupos types `5901234123457` and Enter there, like a USB scanner. If the terminal you ran the command in still has focus when the countdown ends, emupos cancels the scan instead of typing it into your shell. This needs the Accessibility permission on macOS ([guide](macos-accessibility.md)) and an X11 session on Linux ([guide](linux-x11.md)). On Windows emupos cannot tell whether the terminal still has focus, so make sure you click the target window in time ([guide](windows-keyboard.md)).

## 8. Stop

Press Ctrl+C in the first terminal. emupos closes its ports and removes its serial links.

If a step did not work, run `emupos doctor`: it checks your machine and `./emupos.yaml`, and prints a fix for every problem it finds.

Next, write your own configuration with `emupos config init` ([reference](configuration.md)), and point your POS at the endpoints `emupos run` prints.
