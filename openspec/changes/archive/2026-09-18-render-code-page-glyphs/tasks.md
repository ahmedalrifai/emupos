## 1. Glyph generator

- [x] 1.1 In `scripts/generate_glyphs.py`, set `CODE_PAGES` to the 12 codecs the shipped profiles name: `cp437`, `cp850`, `cp852`, `cp858`, `cp860`, `cp863`, `cp865`, `cp866`, `cp1252`, `cp720`, `cp864`, `cp1256`. Make `needed_code_points()` skip bytes a code page leaves undefined (`UnicodeDecodeError`); PC864 has 6 and WPC1252 has 5.
- [x] 1.2 Download misc-fixed alongside Spleen, pinned the same way: `https://www.x.org/releases/individual/font/font-misc-misc-1.1.3.tar.xz`, SHA-256 `79abe361f58bb21ade9f565898e486300ce1cc621d5285bec26e14b6a8618fed`. Read `10x20.bdf`, `9x15.bdf` and `COPYING` from it (design D1).
- [x] 1.3 Place a misc-fixed glyph in the emupos cell with the two fonts' baselines aligned, computing the offset from each BDF's `FONTBOUNDINGBOX` rather than hard-coding it: Font A starts 3 rows down with 1 dot of padding each side, Font B starts at the top edge with no padding (design D2).
- [x] 1.4 Extend a joining letter's connecting stroke into Font A's padding columns: read the form from `unicodedata.decomposition`, fill the right padding for `<final>` and `<medial>`, the left padding for `<initial>` and `<medial>`, and neither otherwise, by copying the ink of the glyph's outermost column on that side (design D3).
- [x] 1.5 Take each glyph from the first source that has it — Font A: `spleen-12x24`, `spleen-16x32` downscaled, then `10x20.bdf`; Font B: `spleen-8x16`, then `9x15.bdf` — so every glyph emupos renders today stays byte-identical (design D1).
- [x] 1.6 Name both fonts in the generated table header and include both licence texts, Spleen's BSD-2-Clause and misc-fixed's public-domain notice.
- [x] 1.7 Run `uv run scripts/generate_glyphs.py` and commit the regenerated `font-a-12x24.hex` and `font-b-9x17.hex`: 575 glyphs per font, up from 251. Check by eye that Arabic words in the tables join and that a PC437 line is unchanged.

## 2. Simulator

- [x] 2.1 In `glyphs.py`, list the 12 code pages in `GLYPH_CODE_PAGES` and update the module docstring to name both font sources.
- [x] 2.2 Confirm no change is needed in `model.py`: `cell_image` already draws the placeholder for a byte with no glyph, and `_select_code_page` already emits the event only for a code page outside `GLYPH_CODE_PAGES` or a number missing from the profile map (design D5).

## 3. Tests

- [x] 3.1 In `test_render.py`, rewrite the code-page tests for the new behaviour (design D7): PC864 on `epson-tm-t20iii` renders the U+FE8D glyph in one 12 × 24 cell and emits no event; `1b 74 16` on `rongta-rp326` renders the same glyph and emits no event; a byte PC864 leaves undefined (`ff`) renders a placeholder with no event; a number missing from the map still emits the event.
- [x] 3.2 Add a test that a line of mixed Latin and Arabic keeps one cell per byte in the order received, from `34 2e 37 35 20 df e8 e5 cc e5 e4 c7`, in the image and in the text dump.
- [x] 3.3 Add a table test over `GLYPH_CODE_PAGES`: for each code page, every byte that decodes has a glyph in both font tables, except the known gaps listed per font in design D5 — Font A lacks 12 (the 8 bytes PC720 maps to C1 controls, and U+200C–U+200F), Font B lacks 18 (those 8 bytes, U+200E and U+200F, and WPC1256's 8 Urdu letters). It fails when a code page is added without regenerating the tables.
- [x] 3.4 Rework the `handwritten/code-page-placeholder` case onto a code-page number missing from the profile's map, so the placeholder path stays covered, and update its `notes.md`.
- [x] 3.5 Add a handwritten case per code page printing its bytes `80` to `ff`, and one printing a line of mixed Latin and Arabic. Generate the expected files with `EMUPOS_UPDATE_CASES=1` and review each image.
- [x] 3.6 Run the full suite and confirm the only golden images that changed are the ones that used a non-PC437 code page.

## 4. Documentation

- [x] 4.1 Add a misc-fixed entry to `NOTICE`: X.Org `font-misc-misc` 1.1.3, public domain, used for the Arabic and remaining glyphs in `src/emupos/printer/escpos/fonts/`.
- [x] 4.2 Update the "Glyph shapes are approximate" row of the README limits table: name the 12 code pages that have glyphs, keep the note that shapes are approximate, and say that bytes print in the order received — emupos does not reorder right-to-left text or join letters, because the printer does not either, so the POS shapes and reverses Arabic before sending it.
- [x] 4.3 Update the code-page note in `docs/protocols/escpos-status.md:243`, which still says only PC437 has glyphs, with the same right-to-left sentence.
- [x] 4.4 Update the `printer.codepage.unsupported` row in `docs/automation.md` to describe when it now fires: a number missing from the profile's map, or a code page emupos has no glyph table for.
- [x] 4.5 Check `docs/configuration.md` for claims about which code pages render, and update if needed.
- [x] 4.6 Reword `cases/captured/receipt-printer-encoder-arabic-codepage/notes.md`: its capture no longer "exercises the unsupported code page event only", because selecting 37 on the Epson profile now emits nothing. The bytes are `3f` question marks, so its image and text dump do not change.
