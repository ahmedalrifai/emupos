# python-escpos-graphics-image

Captured on macOS (September 2026) with `spikes/printer-capture/capture.py` from python-escpos 3.1 (MIT), profile TM-T20II.
Job `graphics-image` in `spikes/printer-capture/python_escpos_jobs.py`. Re-captured on
2026-09-14 with the same script: the bytes are identical.

Commands in the input (count):

- ESC d (1)
- GS ( L fn 112 (1): store a 160 x 64 dot raster image (tone 48, scale 1 x 1, colour 49)
- GS ( L fn 50 (1): print the stored graphics
- GS V m=0 (1)

`impl="graphics"` uses the buffered graphics functions of GS ( L. Since task 5.11 emupos
renders them: the receipt holds the 160 x 64 image, left-aligned. Before that change both
commands were reported as unknown and no receipt was produced.
