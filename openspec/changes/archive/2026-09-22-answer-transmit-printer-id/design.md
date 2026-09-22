## Context

`GS I n` (`1d 49 n`) asks a printer who it is. The Epson reference groups the answers into three
kinds, each with its own framing ([GS I][gs-i]):

| Kind | n | Reply |
|---|---|---|
| Printer ID | 1, 49 (model), 2, 50 (type), 3, 51 (version) | one byte |
| Printer information A | 33, 35, 36, 96, 110 | `3d` + identifier (= n) + data + `00` |
| Printer information B | 65–69, 111, 112 | `5f` + data + `00`, or `5f 00` when the printer has no value |

The TM-T20III accepts n = 1, 2, 49, 50, 35 and 65–69. Its published values are model ID `63` hex
(99 decimal), type ID with bit 1 set for the installed autocutter and bits 2, 3, 5 and 6 not
supported, column emulation mode `"0"` for the standard column mode and `"1"` for 42 columns, and
model name `TM-T20III`. The maker name is `EPSON` on every Epson model.

Today the tokenizer recognises `GS I` and consumes its parameter (`tokenizer.py:190`), and the
command falls through `_print` to `PrintModel.process`, which publishes `printer.command.unknown`.
Status replies already have a home: `escpos/status.py` turns state into reply bytes, and
`printer.py` decides when to write them.

[gs-i]: https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/gs_ci.html

## Goals / Non-Goals

**Goals:**

- A POS that sends `GS I` to `epson-tm-t20iii` gets the bytes a TM-T20III sends, so it can identify
  the printer and stop waiting.
- The values are per model and readable by whoever writes a profile, including a user-provided one.
- A profile whose values are unknown behaves exactly as it does today.

**Non-Goals:**

- Firmware versions and serial numbers set per device in `emupos.yaml`.
- The type ID bits for multi-byte characters and a connected customer display.
- `GS ( A` self-test printing, which the Epson page mentions as another way to read the firmware
  version.

## Decisions

### D1. The values live in the printer profile, in an optional `printer_id` block

A profile already carries what differs per model: geometry, fonts, code-page numbers, drawer
polarity and serial framing. The `GS I` values are the same kind of fact, and putting them there
means a user-provided profile for an unlisted model can carry its own values without touching
emupos.

```yaml
printer_id:
  model: 0x63                  # GS I n = 1, 49. Epson: TM-T20III, hex 63 / decimal 99
  autocutter: true             # type ID (n = 2, 50) bit 1
  column_emulation_mode: true  # this model answers n = 35
  maker: EPSON                 # n = 66
  name: TM-T20III              # n = 67
```

The model name key is `name`, not `model_name`, because Pydantic reserves the `model_` prefix on a
`BaseModel`. It sits inside `printer_id`, so it does not collide with the profile's own `name`,
which is the human-readable model name shown in `emupos devices`.

The whole block is optional. Absent, the printer answers no `GS I` at all, which keeps
`rongta-rp326` and `xprinter-xp80t` exactly as they are until someone reads their manuals.

Alternatives considered: a table in `status.py` keyed by profile name (invisible to a user-provided
profile, and puts model facts in code); the values in `emupos.yaml` per device (they describe a
model, not an installation, and every user would have to repeat them).

### D2. The type ID reports only the autocutter; the other bits stay 0

Bit 0 (multi-byte characters) and bit 2 (a connected DM-D customer display) are false for every
built-in profile, and bit 2 only becomes interesting when emupos simulates a customer display
(issue #19). Bits 3–7 are reserved or fixed at 0 in the reference. So one boolean, `autocutter`,
produces the byte: `02` when true, `00` when false. A profile that needs another bit can gain a
field then, and the reply builder is the only place to change.

### D3. `column_emulation_mode` is a boolean, not the value reported

Epson defines n = 35 as `"0"` for the standard column mode and `"1"` for 42 columns. emupos always
renders the standard mode at the profile's `width_dots`, so `"0"` is the only answer that matches
what it prints, and a profile that could set `"1"` could make emupos report a mode it does not
render. The field therefore says whether the model answers n = 35 at all; the value is always `"0"`.
Models that do not list n = 35, such as the TM-T88V, leave it out and get the unknown-command path.

### D4. `status.gs_i(n, printer_id)` builds the reply, mirroring `gs_r`

A pure function from n and the profile block to bytes, or `None` when there is nothing to answer.
`None` covers both "the profile has no values" and "this n has no value", so `printer.py` has one
rule: no bytes means the existing `printer.command.unknown` path. The function holds the three
framings from the table above, so the reference layout stays in one file with the `DLE EOT`, `GS r`
and ASB layouts.

### D5. Information B without a value is `5f 00`, not silence

Epson: "If the printer information is not prepared, [Header + NUL] (2 bytes) are sent." A simulator
has no firmware build, no serial number and no language font, so n = 65, 68 and 69 answer `5f 00`.
That is a true answer from a real printer's vocabulary, and it keeps a POS that waits for a reply
moving instead of timing out — the whole point of the issue.

### D6. `GS I` is handled in `_print`, not `_realtime`

`GS I` is not a real-time command, so it belongs with the print data: held while a paper-out,
cover-open or offline fault blocks printing, answered in order once the fault clears, and written
only to the connection that asked. Putting the case next to `GS r` in `_print` gets all of that from
the existing `_submit` and `_write` paths, with no new state.

### D7. Tests assert the exact bytes

`test_printer.py` already drives the printer with byte strings and asserts writes. The new tests
follow it: each n value's reply for `epson-tm-t20iii`, no reply plus an unknown event for n = 3 and
for `rongta-rp326`, and a `GS I` sent while paper-out is answered only after the fault clears.

## Risks / Trade-offs

- **The Rongta and Xprinter values are still missing** → Their profiles keep today's behaviour, and
  the issue records what is needed: their manuals, or `GS I` sent to a real printer with the reply
  recorded. Nothing in this change has to be revisited to add them later — a `printer_id` block in
  the profile is the whole task.
- **A POS could read the model ID and take an Epson-specific path** it would not take against the
  other profiles → That is the point: the simulator answers what the profile's real model answers.
- **`model: 0x63` is written in hex in YAML and read as the integer 99** → The profile comments give
  both forms, and the spec and tests state the byte in hex, as every other ESC/POS byte in this
  repo is stated.
