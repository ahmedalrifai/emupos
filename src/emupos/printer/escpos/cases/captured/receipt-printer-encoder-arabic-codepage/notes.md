# receipt-printer-encoder-arabic-codepage

Captured on macOS (September 2026) with `spikes/printer-capture/capture.py` from @point-of-sale/receipt-printer-encoder 3.0.3 (MIT), printerModel epson-tm-t20iii.
Job `arabic-codepage` in `spikes/printer-capture/node_jobs.mjs`.

Commands in the input (count):

- CR (6)
- ESC @ (1)
- ESC M (1)
- ESC t (1)
- FS . (1)
- GS V m=0 (1)
- LF (6)
- text (1)

Observed: the encoder selects PC864 as `1b 74 25` (37, Epson numbering) but sent `3f` (`?`)
for every Arabic letter, so no Arabic reaches the printer. The receipt shows what the POS sent,
question marks included; PC864 itself has glyphs, which `handwritten/code-page-pc864` covers.
