## Why

POS software and printer drivers send `GS I n` (`1d 49 n`) to learn which printer they are talking
to: its model, whether it has an autocutter, the maker and the model name (issue #31). Epson's
reference tells the host to wait for the reply before sending more data, so a POS that asks a
simulated printer can hang until it times out.

Since #29 emupos recognises `GS I` and consumes it with its parameter, but sends no reply and
publishes `printer.command.unknown`. The bytes a printer sends back differ per model, so they
belong with the other per-model values in the device profile.

## What Changes

- **A printer profile can carry the values `GS I` reports**, in a new optional `printer_id` block:
  the printer model ID, whether an autocutter is installed, the column emulation mode, the maker
  name and the model name. A profile without the block is unchanged in every way.
- **`epson-tm-t20iii` gets the values Epson publishes for the TM-T20III**: model ID `63`, autocutter
  installed, column emulation mode `"0"`, maker `EPSON`, model name `TM-T20III`.
- **`rongta-rp326` and `xprinter-xp80t` keep sending no reply**, because their manuals have not been
  read yet. They keep publishing `printer.command.unknown` for every `GS I`, exactly as today.
- **The printer answers the n values its profile has a value for**: 1 and 49 (model ID), 2 and 50
  (type ID), 35 (column emulation mode) and 66 and 67 (maker and model name). n = 65, 68 and 69
  (firmware version, serial number and language font) are answered with the two bytes a real printer
  sends when it has no value prepared, `5f 00`, because a simulator has no firmware build and no
  serial number to report.
- **Every other n is unchanged**: no reply and a `printer.command.unknown` event, which is what a
  developer needs to see when a POS asks for something emupos does not answer.
- **The reply waits behind a blocking fault.** `GS I` is not a real-time command, so its reply is
  sent after the paper-out, cover-open or offline fault clears and the data received before it has
  been processed, the same as `GS r`. This falls out of the existing held-data path.

Not in this change, to keep it to the issue's scope:

- Setting the firmware version or serial number per device in `emupos.yaml`. A profile that wants
  its own values can set them once the need is real; until then every printer answers `5f 00`, which
  is what an unprepared real printer answers.
- The type ID bits for multi-byte characters and a connected customer display. No shipped profile
  sets either, and the customer display is issue #19.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `receipt-printer`: a new requirement, "Transmit printer ID", covering the `GS I` replies, the n
  values without a value, and the fault behaviour. The "Command recognition" requirement is
  unaffected: `GS I` is already recognised and consumed with its parameter.
- `configuration`: "Device profiles" gains the optional `printer_id` block in the list of what a
  printer profile defines, and the rule that a profile without it makes the printer send no reply
  to `GS I`.

## Impact

- `src/emupos/config.py`: a `PrinterId` model and the optional `printer_id` field on
  `PrinterProfile`. The JSON Schema export follows from the model.
- `src/emupos/printer/escpos/status.py`: the reply bytes for each n, next to `gs_r`.
- `src/emupos/printer/printer.py`: a `GS I` case in `_print`, beside the `GS r` case.
- `src/emupos/profiles/printers/epson-tm-t20iii.yaml`: the new block, with the Epson reference cited
  like the geometry and code-page numbers above it.
- Tests: `test_printer.py` for the replies, the held-behind-a-fault case and the profiles without
  values; `test_config.py` for the new profile field.
- Docs: `docs/protocols/escpos-status.md` — `GS I` moves out of the "consumed and reported as
  unknown" list into a section of its own; `docs/configuration.md` — the printer profile key table.
- No API, CLI, event or dependency changes: no new event type, and `printer.command.unknown` keeps
  its name and data.
