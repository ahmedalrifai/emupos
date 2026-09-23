## 1. Profile

- [x] 1.1 In `config.py`, add a frozen `PrinterId` model beside `PrinterProfile`: `model` (int, 0–255), `autocutter` (bool), `column_emulation_mode` (bool, default false), `maker` (str) and `name` (str, not `model_name`: Pydantic reserves the `model_` prefix). Add `printer_id: PrinterId | None = None` to `PrinterProfile` (design D1, D2, D3).
- [x] 1.2 Add the block to `src/emupos/profiles/printers/epson-tm-t20iii.yaml` with `model: 0x63`, `autocutter: true`, `column_emulation_mode: true`, `maker: EPSON`, `name: TM-T20III`, and a comment citing the Epson GS I page the way the geometry and code-page comments above it cite theirs. Leave `rongta-rp326` and `xprinter-xp80t` untouched.
- [x] 1.3 Confirm every built-in profile still loads and `emupos config validate` still passes on the starter configuration and the demo configuration. `emupos config schema` needs no change: it exports the `emupos.yaml` model, which does not include profiles.

## 2. Replies

- [x] 2.1 In `escpos/status.py`, add `gs_i(n, printer_id)` returning the reply bytes or `None`, next to `gs_r`: n = 1, 49 → the model ID byte; n = 2, 50 → the type ID byte, bit 1 from `autocutter`, other bits 0; n = 35 → `3d 23 30 00` when `column_emulation_mode`, else `None`; n = 66, 67 → `5f` + maker or model name + `00`; n = 65, 68, 69 → `5f 00`; anything else, and `printer_id is None` → `None` (design D4, D5). Cite the GS I reference page in the module docstring's source list.
- [x] 2.2 In `printer.py`, add a `"GS I"` case to `_print` beside `"GS r"`: write `status.gs_i(token.params[0], self._profile.printer_id)` when it is not `None` and return; otherwise fall through to the existing unknown-command path (design D6).
- [x] 2.3 Check that the maker and model name encode as ASCII, and that a non-ASCII name in a user-provided profile fails validation rather than at reply time.

## 3. Tests

- [x] 3.1 In `test_printer.py`, assert the exact reply bytes for n = 1, 49, 2, 50, 35, 66, 67, 65, 68 and 69 on `epson-tm-t20iii`, and that none of them emits `printer.command.unknown`.
- [x] 3.2 Assert no reply and a `printer.command.unknown` event carrying `1d 49 03` for n = 3 on `epson-tm-t20iii`, and the same for n = 1 on a profile without the block.
- [x] 3.3 Assert that `GS I` sent while paper-out is answered only after the fault is cleared, following the existing held-data tests, and that the reply goes only to the connection that asked when two connections are open.
- [x] 3.4 In `test_config.py`, cover a profile with the block, a profile without it, and a rejected value (`model: 256`).
- [x] 3.5 Run the full suite and the type checker.

## 4. Documentation

- [x] 4.1 In `docs/protocols/escpos-status.md`, remove `GS I` from the "consumed and reported as unknown" list and add a short section for it: the reply per n, that the values come from the profile, that only `epson-tm-t20iii` has them today, and that a profile without them answers nothing. Add the GS I page to the reference table at the top.
- [x] 4.2 In `docs/configuration.md`, add `printer_id` to the printer profile key table, with its keys and the note that it is optional.
- [x] 4.3 Archive the change with `openspec archive answer-transmit-printer-id` in the implementation commit.
