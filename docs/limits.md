# Hard limits

Some things cannot be simulated in software, or not on every operating system:

| Limit | What it means for you |
|---|---|
| Virtual serial ports on Windows need a driver | Windows has no built-in virtual serial port pairs, so serial devices there need a port pair driver such as com0com, which Secure Boot blocks on current Windows 11, or two USB serial adapters (see [windows-serial.md](windows-serial.md)). |
| Simulator-created serial ports are not listed | The ports emupos creates on macOS and Linux do not appear in serial port lists or pickers, including the browser's Web Serial API. Open them by path. A browser POS that uses Web Serial cannot reach them. |
| USB devices are not emulated | USB printer-class devices and HID POS scanners cannot be emulated in software. emupos offers the same devices over TCP, serial and keyboard input. |
| No keyboard scanning on Wayland | Wayland does not let one program type into another's windows. Use a serial scanner, or an X11 session. |
| macOS needs the Accessibility permission for keyboard scans | Without it macOS silently drops the keystrokes, so emupos refuses the scan and tells you which app to allow. |
| Windows print queues are one-way | A POS that prints through a Windows print queue never receives status replies such as paper out. Test status over TCP. Windows also takes up to 10 minutes to show a new fault on the queue. |
| Windows scans into elevated windows are lost | Windows drops keystrokes sent to a window running as administrator from a normal-user emupos, and reports them as delivered. Run both at the same privilege level. |
| Glyph shapes are approximate | Receipt geometry is dot-accurate (paper width, columns, line breaks, images, barcode module sizes), but characters are drawn with open-licensed bitmap fonts, not the printer's own. The code pages the built-in profiles name have glyphs: PC437, PC850, PC852, PC858, PC860, PC863, PC865, PC866, WPC1252, PC720, PC864 and WPC1256. Another code page prints placeholders, while the text dump still shows the characters. |
| Right-to-left layout belongs to the POS | Like the printers it simulates, emupos prints the bytes it receives left to right, one character cell each: it never reorders them and never joins Arabic letters. A POS shapes and reverses its Arabic before sending it, so text that comes out backwards on paper comes out backwards here too. |
| Virtual serial pairs ignore baud rate and parity | Data passes whatever settings your POS chooses, while a real device would misread the bytes. Watch for emupos's framing warnings, which cover what the operating system exposes (macOS: baud rate, data bits, parity; Linux: baud rate only). |
