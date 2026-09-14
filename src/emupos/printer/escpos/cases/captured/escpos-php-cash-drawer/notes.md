# escpos-php-cash-drawer

Captured on macOS (September 2026) with `spikes/printer-capture/capture.py` from escpos-php 5.0 (MIT), PHP 8.4 in Docker, default capability profile.
Job `cash-drawer` in `spikes/printer-capture/php_jobs.php`.

Commands in the input (count):

- ESC @ (1)
- ESC p m=48 (1)
- ESC p m=49 (1)

escpos-php sends `m` as the ASCII digits `0` and `1` (48 and 49), where python-escpos sends 0 and 1. Both select pin 2 and pin 5.
