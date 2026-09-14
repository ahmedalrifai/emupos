# epson-tm-mac-driver-receipt

Produced on macOS 26.5 (September 2026) by Epson's TM Series Printer Driver for Mac 3.0.1 (`rastertotmtr`, PPD "EPSON TM Thermal (203dpi)", paper "Roll paper 80 x 200 mm", "Cut per job", "Open drawer #1"). These are the bytes a macOS print queue using that driver sends to the printer: the page is printed as one graphics image. A three-line text file was rasterised with `cupsfilter -m application/vnd.cups-raster` and passed to the driver's filter.

Commands in the input (count):

- ESC $ (1)
- ESC = (1)
- ESC @ (1)
- ESC J (2)
- ESC c 0 (1)
- ESC c 1 (1)
- ESC c 3 (1)
- ESC p m=0 (1)
- GS ( L fn=50 (1)
- GS 8 L (1)
- GS P (1)
- GS V m=66 (1)

The driver starts with ESC c 0 and ESC c 1 (paper type: roll paper). Before emupos knew these two commands, their parameters printed as the text `01` at the top of the receipt.
