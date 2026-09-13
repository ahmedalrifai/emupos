# python-escpos-graphics-image

Captured on macOS (September 2026) with `spikes/printer-capture/capture.py` from python-escpos 3.1 (MIT), profile TM-T20II.
Job `graphics-image` in `spikes/printer-capture/python_escpos_jobs.py`.

Commands in the input (count):

- ESC d (1)
- GS ( L (2)
- GS V m=0 (1)

Observed: `impl="graphics"` uses GS ( L (store and print graphics data), which emupos does not
render: both commands are consumed and reported, and no receipt is produced.
