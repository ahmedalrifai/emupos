# ESC/POS status replies

A simulated printer answers status requests the way an Epson TM printer does. Every reply is computed from the printer's current state, so when you make the printer run out of paper with `emupos fault set front paper-out`, your POS reads "paper out" in the status bytes, exactly as it would from a real printer.

This page lists the bytes emupos sends back, bit by bit. The bit layouts follow the Epson ESC/POS Command Reference for TM printers:

| Command | Reference page |
|---|---|
| `DLE EOT` | <https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/dle_eot.html> |
| `GS r` | <https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/gs_lr.html> |
| `ESC v`, `ESC u` (obsolete status requests) | <https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/esc_lv.html>, <https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/esc_lu.html> |
| `GS a` (Automatic Status Back) | <https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/gs_la.html> |
| `ESC p` (drawer kick) | <https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/esc_lp.html> |
| `DLE DC4 fn 1` (real-time drawer pulse) | <https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/dle_dc4_fn1.html> |

Other commands are cited in the source: `src/emupos/printer/escpos/tokenizer.py` names the reference page of every command it recognises (`https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/<page>.html`).

All bytes on this page are hexadecimal.

## The state behind every reply

| State | How you change it | Effect on printing |
|---|---|---|
| `paper-near-end` | `emupos fault set front paper-near-end` | Still prints. |
| `paper-out` | `emupos fault set front paper-out` | Blocks printing. |
| `cover-open` | `emupos fault set front cover-open` | Blocks printing. |
| `offline` | `emupos fault set front offline` | Blocks printing. |
| Drawer open or closed | Opened by the POS (`ESC p`, `DLE DC4 fn 1`); closed with `emupos drawer close` | None. |

`emupos fault clear front <fault>` clears a fault. The same actions are available through the control API (`PUT` and `DELETE /api/v1/devices/{id}/faults/{fault}`). Faults are independent: several can be active at once.

While a blocking fault is active, the printer keeps accepting bytes but holds print data and ordinary commands, in order, without printing them. Clearing the last blocking fault processes what was held.

**Real-time commands are never held.** `DLE EOT` and `DLE DC4` are answered as soon as they arrive, even while printing is blocked. `GS r`, `ESC v`, `ESC u`, `GS a` and `ESC p` are ordinary commands: while printing is blocked they wait with the print data. Bytes inside another command's data (for example image data that happens to contain `10 04 01`) are part of that command, never a status request.

## `DLE EOT n` — real-time status (`10 04 n`)

The reply is one byte. Bit 1 and bit 4 are always 1 and bits 0 and 7 are always 0, so a reply with nothing to report is `12`.

### n = 1: printer status

| Bit | Value | Meaning | emupos sets it when |
|---|---|---|---|
| 2 | `04` | Drawer kick-out connector pin 3 is high | the drawer sensor is high (see [Cash drawer](#cash-drawer-and-pin-3)) |
| 3 | `08` | Offline | `offline`, `cover-open` or `paper-out` is active |
| 5 | `20` | Waiting for online recovery | never |
| 6 | `40` | Paper feed button pressed | never |

### n = 2: offline cause

| Bit | Value | Meaning | emupos sets it when |
|---|---|---|---|
| 2 | `04` | Cover is open | `cover-open` is active |
| 3 | `08` | Paper is being fed by the feed button | never |
| 5 | `20` | Printing stopped because of paper end | `paper-out` is active |
| 6 | `40` | Error occurred | never |

### n = 3: error cause

| Bit | Value | Meaning | emupos sets it when |
|---|---|---|---|
| 2 | `04` | Recoverable error | never |
| 3 | `08` | Autocutter error | never |
| 5 | `20` | Unrecoverable error | never |
| 6 | `40` | Automatically recoverable error | never |

No simulated fault is an error, so the reply to `10 04 03` is always `12`.

### n = 4: roll paper sensor

| Bits | Value | Meaning | emupos sets them when |
|---|---|---|---|
| 2 and 3 | `0c` | Roll paper near end | `paper-near-end` or `paper-out` is active |
| 5 and 6 | `60` | Roll paper not present | `paper-out` is active |

### Replies by state

With the drawer sensor low (the drawer closed, with the built-in profiles):

| Active fault | `10 04 01` | `10 04 02` | `10 04 03` | `10 04 04` |
|---|---|---|---|---|
| none | `12` | `12` | `12` | `12` |
| `paper-near-end` | `12` | `12` | `12` | `1e` |
| `paper-out` | `1a` | `32` | `12` | `7e` |
| `cover-open` | `1a` | `16` | `12` | `12` |
| `offline` | `1a` | `12` | `12` | `12` |

When the drawer sensor is high, add `04` to the `10 04 01` reply: `16` with no faults, `1e` with `cover-open`. The drawer bit does not depend on faults.

### Other values of n

For any other n, emupos sends nothing and publishes a `printer.command.unknown` event. For example `10 04 05` followed by `10 04 01` gets exactly one byte back: the reply to `10 04 01`.

## `GS r n` — transmit status (`1d 72 n`)

The reply is one byte, with no fixed bits.

### n = 1 or 49: paper sensor

| Bits | Value | Meaning | emupos sets them when |
|---|---|---|---|
| 0 and 1 | `03` | Roll paper near end | `paper-near-end` or `paper-out` is active |
| 2 and 3 | `0c` | Roll paper not present | `paper-out` is active |

Replies: `00` with no paper fault, `03` with `paper-near-end`, `0f` with `paper-out`.

### n = 2 or 50: drawer kick-out connector

| Bit | Value | Meaning |
|---|---|---|
| 0 | `01` | Pin 3 is high |

Replies: `00` while pin 3 is low, `01` while it is high.

### Other values of n

Other values (for example ink status) get no reply and publish a `printer.command.unknown` event.

`GS r` is not a real-time command. While `cover-open`, `paper-out` or `offline` is active, its reply is sent only after the fault is cleared.

### `ESC v` and `ESC u n` (obsolete)

Older POS software asks for the same bytes with these commands, and emupos answers them like `GS r`, holding them while printing is blocked:

| Request | Reply |
|---|---|
| `ESC v` (`1b 76`) | the paper sensor byte of `1d 72 01` |
| `ESC u n` (`1b 75 n`), n = 0 or 48 | the drawer byte of `1d 72 02` |

`ESC u` with any other n gets no reply and publishes a `printer.command.unknown` event.

## `GS a n` — Automatic Status Back (`1d 61 n`)

Automatic Status Back (ASB) makes the printer push a 4-byte status by itself.

- `GS a n` with n other than 0 turns ASB on **for the connection that sent it**. emupos sends the current 4-byte status at once, then a new one each time a status category enabled by n changes.
- `GS a 0` turns it off. `ESC @` also turns it off, and every new connection starts with it off.
- Other connections to the same printer are not affected.

### The bits of n

| Bit of n | Value | Category | Changes in emupos when |
|---|---|---|---|
| 0 | `01` | Drawer kick-out connector | the drawer opens or closes |
| 1 | `02` | Online/offline | `offline`, `cover-open` or `paper-out` changes |
| 2 | `04` | Errors | never |
| 3 | `08` | Roll paper sensor | `paper-near-end` or `paper-out` changes |
| 6 | `40` | Panel switch | never |

So `1d 61 ff` reports every change, while `1d 61 01` reports only the drawer.

### The four status bytes

| Byte | Value | Meaning | emupos sets it when |
|---|---|---|---|
| 1st | `10` | Fixed | always |
| 1st | `04` | Drawer kick-out connector pin 3 is high | the drawer sensor is high |
| 1st | `08` | Offline | `offline`, `cover-open` or `paper-out` is active |
| 1st | `20` | Cover is open | `cover-open` is active |
| 1st | `40` | Paper being fed by the feed button | never |
| 2nd | `01` | Waiting for online recovery | never |
| 2nd | `02` | Paper feed button pushed | never |
| 2nd | `04` | Recoverable error | never |
| 2nd | `08` | Autocutter error | never |
| 2nd | `20` | Unrecoverable error | never |
| 2nd | `40` | Automatically recoverable error | never |
| 3rd | `03` | Roll paper near end | `paper-near-end` or `paper-out` is active |
| 3rd | `0c` | Roll paper not present | `paper-out` is active |
| 4th | — | — | always `00` |

| State | ASB status |
|---|---|
| no faults, pin 3 low | `10 00 00 00` |
| pin 3 high | `14 00 00 00` |
| `paper-near-end` | `10 00 03 00` |
| `paper-out` | `18 00 0f 00` |
| `cover-open` | `38 00 00 00` |
| `offline` | `18 00 00 00` |

### Example

`>` is what the POS sends, `<` is what emupos sends back:

```
> 1d 61 ff            turn on ASB for everything
< 10 00 00 00         current status
                      (emupos fault set front cover-open)
< 38 00 00 00         offline, cover open
> 10 04 01 10 04 02   real-time status while the cover is open
< 1a 16
> 1d 72 01            GS r: held, printing is blocked
                      (emupos fault clear front cover-open)
< 10 00 00 00 00      the new ASB status, then the held GS r reply
```

## Cash drawer and pin 3

Every printer has one cash drawer. The POS opens it with a pulse on the drawer kick-out connector:

| Command | Bytes | Pin | Pulse ON time | Held while printing is blocked? |
|---|---|---|---|---|
| `ESC p m t1 t2` | `1b 70 m t1 t2` | m = `00` or `30` ("0"): pin 2; m = `01` or `31` ("1"): pin 5 | t1 × 2 ms | Yes |
| `DLE DC4 fn 1` | `10 14 01 m t` | m = `00`: pin 2; m = `01`: pin 5; t from 1 to 8 | t × 100 ms | No, it opens at once |

A pulse on either pin opens the same drawer. Other parameter values open nothing and publish `printer.command.unknown`. The drawer stays open until you close it with `emupos drawer close` or `POST /api/v1/devices/{id}/drawer/close`: it never closes by itself.

The drawer's switch is read on connector **pin 3**. Drawers differ in which level means "open", so the level is configurable with `drawer: { sensor_open_level: high | low }` in `emupos.yaml`. When it is not set, the printer profile decides; all built-in profiles use `high`.

| `sensor_open_level` | Drawer | Pin 3 | `10 04 01` bit 2 | `1d 72 02` | ASB 1st byte bit 2 |
|---|---|---|---|---|---|
| `high` | open | high | 1 (`16`) | `01` | 1 (`14`) |
| `high` | closed | low | 0 (`12`) | `00` | 0 (`10`) |
| `low` | open | low | 0 (`12`) | `00` | 0 (`10`) |
| `low` | closed | high | 1 (`16`) | `01` | 1 (`14`) |

The replies in brackets assume no active fault.

## What happens to each command

The printer recognises a command by its bytes and consumes it completely, including its parameters and data, so the next command is always found correctly. What happens next depends on the command.

### Rendered or acted on

| Commands | What emupos does |
|---|---|
| Printable text (`20`–`ff`), `LF`, `ESC d`, `ESC J`, `ESC 2`, `ESC 3` | Prints text and feeds paper; wraps text that does not fit the line |
| `GS T` | Returns to the start of the line: n = 1 or 49 prints the line first (like `LF`), n = 0 or 48 discards it; ignored at the start of a line |
| `ESC @` | Resets print settings to the profile defaults and discards the unprinted line |
| `ESC !`, `ESC E`, `ESC G`, `ESC -`, `ESC M`, `GS !`, `GS B` | Font, bold (double-strike looks the same as bold), underline, character size, reverse printing |
| `ESC a`, `ESC {` | Justification and upside-down printing; ignored when sent in the middle of a line |
| `ESC t` | Selects a code page by the profile's number; see the note below |
| `HT`, `ESC D` | Tabs: moves to the next tab position (every 8 characters by default); the text dump fills the gap with spaces |
| `ESC SP`, `GS L`, `GS W`, `ESC $`, `ESC \` | Right-side character spacing, left margin, print area width, absolute and relative print position |
| `ESC *`, `GS v 0` | Bit images and raster images, dot for dot |
| `GS ( L` / `GS 8 L` fn 112 and fn 50 | Buffered graphics: store a monochrome raster image, then print it. fn 48 and fn 51 report an NV graphics capacity of zero |
| `GS k` | Barcodes: UPC-A, EAN-13, EAN-8, CODE39, ITF and CODE128 (m = 73) |
| `GS w`, `GS h`, `GS H`, `GS f` | Barcode module width, height, and position and font of the human-readable text |
| `GS ( k` with cn = 49 | QR codes: module size (fn 167), error correction (fn 169), store (fn 180), print (fn 181); always printed as model 2 |
| `GS V`, `ESC i`, `ESC m` | Ends the receipt (any cut form; `ESC i` and `ESC m` are Epson's obsolete partial cuts) |
| `ESC p`, `DLE DC4 fn 1` | Opens the drawer |
| `DLE EOT n` (n = 1–4), `GS r n` (n = 1, 2, 49, 50), `ESC v`, `ESC u n` (n = 0, 48), `GS a n` | Status replies, as described above |

The code pages the built-in profiles name have glyphs: PC437, PC850, PC852, PC858, PC860, PC863, PC865, PC866, WPC1252, PC720, PC864 and WPC1256. Selecting a number missing from the profile, or a code page emupos has no glyph table for, publishes `printer.codepage.unsupported`, and bytes `80`–`ff` then print as a placeholder that fills one character cell. A single byte without a glyph inside a code page that has a table prints the same placeholder, without an event. Bytes `20`–`7e` always print as ASCII. The receipt's text dump shows the real characters for code pages emupos has a character mapping for (PC720, PC864 and WPC1256 among them), and U+FFFD otherwise.

Each byte is printed into the next character cell, in the order it arrives. Like a real ESC/POS printer, emupos does not reorder bytes and does not join Arabic letters: a POS shapes its Arabic and reverses it before sending, and what it sends is what the receipt shows.

### Consumed without any effect

These change nothing on a receipt image, so emupos consumes them silently: `CR`, `GS b`, `FS .`, `FS &`, `ESC =`, `ESC c 0`, `ESC c 1`, `ESC c 3`, `ESC c 4`, `ESC c 5`, `ESC U`, `GS P`, `ESC S`, and `ESC r` (print colour: every built-in profile is single-colour, so text asked for in red prints in black, as on a real single-colour printer).

### Consumed and reported as unknown

These are recognised and consumed in full, but not simulated. Each one publishes a `printer.command.unknown` event whose data has the bytes and the command name, and printing continues normally:

- character sets and rotation: `ESC R`, `ESC V`
- page mode: `ESC L` (the printer stays in standard mode), `ESC T`, `ESC W`, `GS $`, `GS \`
- NV graphics and other function commands: `GS ( L` / `GS 8 L` functions other than 48, 50, 51 and 112, other `GS (` commands, `ESC (`, `FS (`
- stored logos and bit images: `FS p`, `GS *`, `GS /` (nothing is printed)
- `GS I` (no reply is sent)
- `GS ( k` symbols other than QR codes, such as PDF417
- `GS k` in other symbologies (UPC-E, CODABAR, CODE93, GS1-128, GS1 DataBar, CODE128 with m = 79); the event names the symbology
- `DLE ENQ`, `DLE DC4` functions other than 1, `DLE EOT`, `GS r` and `ESC u` with other values of n
- `ESC *`, `GS v 0`, `ESC M`, `ESC p` and `GS T` with a mode or parameter they do not accept

Some POS libraries send these. When one of them matters for your receipts, open a device or protocol request. Unknown commands never affect status replies.

### Bytes that form no command

A control byte that starts no recognised command is skipped. After `ESC`, `GS`, `FS` or `DLE`, the following byte is skipped too. Each skip publishes `printer.command.unknown` with the skipped bytes. A command still incomplete when the connection closes is dropped the same way. No byte sequence stops the printer.
