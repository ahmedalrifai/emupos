# Moving to real hardware

Your POS already stores where each device is: a printer address, a serial port name. Moving from emupos to real hardware changes those settings in **your POS**. Nothing in emupos changes, and your integration code stays the same.

| Device | Development, with emupos | Production, real hardware | What you change in your POS |
|---|---|---|---|
| Network receipt printer | `127.0.0.1:9100` | `192.168.1.50:9100` (the printer's IP) | printer address |
| Serial scale | `$TMPDIR/emupos/deli` (macOS/Linux) or a com0com port such as `COM6` (Windows) | `/dev/ttyUSB0` or `COM3` | serial port |
| Serial scanner | `$TMPDIR/emupos/lane2` or a com0com port | the scanner's port, e.g. `COM4` | serial port |
| Keyboard-wedge scanner | keystrokes | keystrokes | nothing |

This holds as long as development and production use the same kind of connection. Watch for these:

- **Use the same transport.** If you develop against TCP port 9100 but deploy a USB-only printer, your POS needs a different code path (USB through a driver or print queue), which is a code change. Choose a network printer for production, or the same printing path in both places.
- **Match the printer brand with the profile.** Vendors number code pages differently: PC864 is 37 on Epson and 22 on Rongta. If your POS sends these numbers, run emupos with the profile of the printer you will deploy (`epson-tm-t20iii`, `rongta-rp326`, `xprinter-xp80t`), so a wrong number shows up during development.
- **Match the serial settings.** Real devices misread bytes sent with the wrong baud rate or parity (a Toledo 8217 scale expects 9600 baud, 7 data bits, even parity). emupos warns when your POS uses other settings, where the operating system lets it see them.
- **Port pickers.** Serial ports that emupos creates on macOS and Linux are not listed by the operating system, so during development you type the path instead of choosing it from a list.

What software cannot simulate at all is listed in [limits.md](limits.md).
