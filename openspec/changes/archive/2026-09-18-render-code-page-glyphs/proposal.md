## Why

Receipt images only have glyphs for PC437 (issue #18). Every other code page the shipped profiles
claim renders placeholder boxes, so a POS that prints Arabic on PC864 (37 on Epson, 22 on Rongta)
cannot check its receipt layout visually, which is most of the value of a rendered receipt.

Two open-licensed bitmap fonts together cover every code page in the shipped profiles. Spleen, which
emupos already bundles, covers the Latin and Cyrillic pages except for 9 characters. The X.Org
misc-fixed fonts (public domain) have all of them, plus every Arabic character of PC864.

## What Changes

- **All 12 code pages the shipped profiles claim get glyph tables**: PC437, PC850, PC852, PC858,
  PC860, PC863, PC865, PC866, WPC1252, PC720, PC864 and WPC1256. Both Font A and Font B.
- **A second font source.** `scripts/generate_glyphs.py` takes each glyph from Spleen where Spleen
  has it, and from misc-fixed (10x20 for Font A, 9x15 for Font B) otherwise. Baselines are aligned
  so a line of mixed Latin and Arabic sits straight.
- **Arabic letters join.** misc-fixed glyphs are 10 dots wide in Font A's 12-dot cell, which would
  leave a 2-dot gap between joined letters. The generator extends the connecting stroke of each
  joining letter form to the cell edge, so words read as words.
- **Right-to-left text is explicitly not emulated**, because real printers do not do it: an ESC/POS
  printer prints the bytes it receives left to right, one cell each, with no reordering and no
  letter joining. The POS shapes and reverses Arabic before sending it; emupos renders what arrives,
  which is what makes a POS that forgot to do so visible during development. Documented in the
  README limits table, `docs/protocols/escpos-status.md` and the spec.
- **`printer.codepage.unsupported` fires in fewer cases.** Selecting PC720, PC864 or WPC1256 on a
  shipped profile no longer emits it and no longer prints placeholders. The event keeps its name and
  its data, and still fires for a code-page number missing from the profile's map, and for a code
  page a custom profile names that emupos has no table for. Bytes a code page leaves undefined, and
  the few characters neither font has, still print a placeholder, without an event.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `receipt-printer`: "Code page selection" changes as follows:
  - the built-in profiles' code pages all have glyph tables, replacing the rule that PC720, PC864
    and WPC1256 have none;
  - a byte with no glyph in a code page that has a table prints a placeholder without an event;
  - printed bytes are placed left to right in the order received, for every code page, with no
    right-to-left reordering and no letter joining.
  - New scenarios cover an Arabic code page rendering glyphs, a line of mixed Latin and Arabic, and
    a character the tables lack.

## Impact

- `scripts/generate_glyphs.py`: the misc-fixed source and its checksum, per-font baseline offsets,
  the joining-stroke extension, the code-page list, and undefined bytes no longer raising.
- `src/emupos/printer/escpos/fonts/font-a-12x24.hex` and `font-b-9x17.hex`: regenerated, 575 glyphs
  each instead of 251, with a header naming both fonts and both licences.
- `src/emupos/printer/escpos/glyphs.py`: `GLYPH_CODE_PAGES` lists the 12 code pages. No change to the
  table format, the loader or `cell_image`.
- `src/emupos/printer/escpos/model.py`: no change; the placeholder path already covers a missing
  glyph.
- Tests: `test_render.py` code-page tests, the `handwritten/code-page-placeholder` case, and new
  cases for the code pages and for mixed Latin and Arabic.
- `NOTICE`: a misc-fixed entry.
- Docs: the "Glyph shapes are approximate" row in `README.md`, the code-page note in
  `docs/protocols/escpos-status.md`, and the event's description in `docs/automation.md`.
- **Dependencies:** none. The fonts are downloaded by the generator when a maintainer runs it, and
  the generated tables are committed; emupos itself gains no dependency.
- No API or configuration changes: no new event type, no profile field.
