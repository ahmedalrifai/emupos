# Windows: keyboard scans

A scanner with `mode: keyboard` types each scan into the focused window, like a USB keyboard-wedge scanner. On Windows emupos does this with `SendInput`. No permission or setup is needed, with the limits below.

## Click the POS window during the countdown

`emupos scan` counts down before it types. On macOS and Linux X11 emupos cancels the scan when the terminal still has focus; **on Windows it cannot tell**, so if the terminal is still focused, the barcode and its Enter are typed into the terminal and run as a command. Click the POS window before the countdown ends, or give yourself more time with `--countdown 10`.

## Run emupos and the POS at the same privilege level

Windows discards keystrokes sent to a window that runs with higher privileges than the sender. A POS started with **Run as administrator** does not receive scans from an emupos that runs as a normal user, and Windows still reports the keystrokes as accepted, so **emupos cannot detect these lost scans**: `emupos scan` reports success and nothing arrives. Run both as a normal user, or both as administrator.

If Windows does report refused keystrokes (for example while the lock screen or a UAC prompt is showing), `emupos run` prints a warning and the scan is not reported as delivered.

## Keyboard layouts

emupos presses the keys that type each character on a US keyboard, with the virtual-key code and scan code a real keyboard sends, so browsers see `KeyboardEvent.code` values such as `Digit5` and `KeyA`. The window's active keyboard layout decides which characters come out, exactly as with a real scanner: with the Arabic (101) layout, digits stay ASCII digits but letters become Arabic letters.

`emupos scan --unicode` (or `"unicode": true` in the API) types the exact characters whatever the layout. These characters carry **no physical key**: a browser reports an empty `code` and, on key up, `key` `Unidentified`. An application that reads key positions or key codes does not see the keys a scanner would press; use `--unicode` only for applications that read the typed text.

## Serial mode instead

A serial scanner writes each scan to a COM port that the POS opens, with no keyboard involved; see [windows-serial.md](windows-serial.md).
