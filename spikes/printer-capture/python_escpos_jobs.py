# /// script
# requires-python = ">=3.13"
# dependencies = ["python-escpos==3.1", "pillow"]
# ///
"""Print a set of typical jobs with python-escpos (MIT) to the capture server.

    uv run spikes/printer-capture/capture.py /tmp/captures &
    uv run spikes/printer-capture/python_escpos_jobs.py

Each job is one connection, sent in the order printed. python-escpos is used only here,
to produce realistic traffic; it is not an emupos dependency.
"""

import time

from escpos.printer import Network
from job_images import arabic_line, checkerboard


def job(name: str) -> Network:
    print(name)
    return Network("127.0.0.1", port=9100, profile="TM-T20II")


def finish(printer: Network) -> None:
    printer.close()
    time.sleep(0.5)  # let the capture server write the file before the next connection


p = job("text-styles")
p.set(align="center", bold=True, double_height=True, double_width=True)
p.text("EMUPOS MARKET\n")
p.set_with_default(align="center")
p.text("12 Example Street\n")
p.set_with_default()
p.text("Item                        Qty   Price\n")
p.text("Tomatoes                      2    3.50\n")
p.set_with_default(bold=True)
p.text("Bold line\n")
p.set_with_default(underline=1)
p.text("Underlined line\n")
p.set_with_default(font="b")
p.text("Font B line with more columns than font A can fit on one line\n")
p.set_with_default(align="right")
p.text("TOTAL 7.00\n")
p.set_with_default(custom_size=True, width=3, height=2)
p.text("3x2\n")
p.set_with_default()
p.ln(2)
p.cut()
finish(p)

p = job("cash-drawer")
p.cashdraw(2)
p.cashdraw(5)
finish(p)

p = job("barcodes")
p.text("EAN-13\n")
p.barcode("4006381333931", "EAN13", height=80, width=2, pos="BELOW", function_type="A")
p.text("CODE128\n")
p.barcode("{BEMUPOS-128", "CODE128", height=60, width=2, pos="BELOW", function_type="B")
p.cut()
finish(p)

p = job("qr")
p.text("Scan me\n")
p.qr("https://example.com", native=True, size=4)
p.cut()
finish(p)

p = job("raster-image")
p.image(checkerboard(), impl="bitImageRaster", center=True)
p.cut()
finish(p)

p = job("column-image")
p.image(checkerboard(), impl="bitImageColumn")
p.cut()
finish(p)

p = job("graphics-image")
p.image(checkerboard(), impl="graphics")
p.cut()
finish(p)

p = job("arabic-image")
p.text("Receipt 1024\n")
p.image(arabic_line(), impl="bitImageRaster")
p.cut()
finish(p)
