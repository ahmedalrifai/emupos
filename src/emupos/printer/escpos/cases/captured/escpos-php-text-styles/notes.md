# escpos-php-text-styles

Captured on macOS (September 2026) with `spikes/printer-capture/capture.py` from escpos-php 5.0 (MIT), PHP 8.4 in Docker, default capability profile.
Job `text-styles` in `spikes/printer-capture/php_jobs.php`.

Commands in the input (count):

- ESC ! (2)
- ESC - (2)
- ESC @ (1)
- ESC E (2)
- ESC M (2)
- ESC a (4)
- ESC d (1)
- GS ! (2)
- GS V m=65 (1)
- LF (9)
- text (9)

escpos-php starts every job with ESC @ and cuts with GS V m=65 (feed, then cut), where python-escpos uses GS V m=0. Its other jobs (barcodes, QR code, images) send the same commands as the python-escpos cases, so they are not kept as cases; `php_jobs.php` re-creates them.
