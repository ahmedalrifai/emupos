# receipt-printer-encoder-image

Captured on macOS (September 2026) with `spikes/printer-capture/capture.py` from @point-of-sale/receipt-printer-encoder 3.0.3 (MIT), printerModel epson-tm-t20iii.
Job `image` in `spikes/printer-capture/node_jobs.mjs`.

Commands in the input (count):

- CR (7)
- ESC * m=33 (3)
- ESC 2 (1)
- ESC 3 (1)
- ESC @ (1)
- ESC M (1)
- FS . (1)
- GS V m=0 (1)
- LF (10)

Observed: before the ESC * rows the encoder sets the line spacing with `1b 33 24`, labelled
"24 dots" in its source, but 0x24 is 36. On a TM-T20III (motion unit 1 dot, see GS P) each
24-dot row is followed by a 12-dot gap, and the rendering shows those gaps.
