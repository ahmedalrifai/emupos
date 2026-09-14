<?php
// Print typical jobs with escpos-php (MIT) to the capture server. escpos-php is not an emupos
// dependency; it runs in Docker (PHP with the intl extension), from the repository root:
//
//   docker build -t escpos-php - <<'DOCKERFILE'
//   FROM php:8.4-cli
//   RUN apt-get update && apt-get install -y --no-install-recommends libicu-dev unzip \
//       && docker-php-ext-install intl && rm -rf /var/lib/apt/lists/*
//   COPY --from=composer:2 /usr/bin/composer /usr/bin/composer
//   DOCKERFILE
//   mkdir -p /tmp/phpjobs
//   docker run --rm -v /tmp/phpjobs:/app -w /app escpos-php composer require mike42/escpos-php:5.0
//   uv run spikes/printer-capture/job_images.py /tmp/phpjobs
//   uv run spikes/printer-capture/capture.py /tmp/captures &
//   docker run --rm -v /tmp/phpjobs:/app -v "$PWD/spikes/printer-capture:/kit" escpos-php \
//       php /kit/php_jobs.php /app host.docker.internal
//
// The arguments after the composer directory are the capture server's host and port (default
// 9100): host.docker.internal reaches the machine running Docker. Each job is one connection, sent in the order printed. Images are loaded with
// escpos-php's own PNG reader (no GD or Imagick).

use Mike42\Escpos\EscposImage;
use Mike42\Escpos\PrintConnectors\NetworkPrintConnector;
use Mike42\Escpos\Printer;

[, $dir, $host, $port] = $argv + [3 => '9100'];
require "$dir/vendor/autoload.php";

function job(string $name): Printer
{
    global $host, $port;
    echo "$name\n";
    return new Printer(new NetworkPrintConnector($host, (int) $port));
}

function finish(Printer $printer): void
{
    $printer->close();
    usleep(500000); // let the capture server write the file before the next connection
}

$checkerboard = EscposImage::load("$dir/checkerboard.png", false, ['native']);
$arabicLine = EscposImage::load("$dir/arabic-line.png", false, ['native']);

$p = job('text-styles');
$p->setJustification(Printer::JUSTIFY_CENTER);
$p->selectPrintMode(Printer::MODE_EMPHASIZED | Printer::MODE_DOUBLE_HEIGHT | Printer::MODE_DOUBLE_WIDTH);
$p->text("EMUPOS MARKET\n");
$p->selectPrintMode();
$p->text("12 Example Street\n");
$p->setJustification();
$p->text("Item                        Qty   Price\n");
$p->text("Tomatoes                      2    3.50\n");
$p->setEmphasis(true);
$p->text("Bold line\n");
$p->setEmphasis(false);
$p->setUnderline();
$p->text("Underlined line\n");
$p->setUnderline(Printer::UNDERLINE_NONE);
$p->setFont(Printer::FONT_B);
$p->text("Font B line with more columns than font A can fit on one line\n");
$p->setFont();
$p->setJustification(Printer::JUSTIFY_RIGHT);
$p->text("TOTAL 7.00\n");
$p->setJustification();
$p->setTextSize(3, 2);
$p->text("3x2\n");
$p->setTextSize(1, 1);
$p->feed(2);
$p->cut();
finish($p);

$p = job('cash-drawer');
$p->pulse(0);
$p->pulse(1);
finish($p);

$p = job('barcodes');
$p->setBarcodeHeight(80);
$p->setBarcodeWidth(2);
$p->setBarcodeTextPosition(Printer::BARCODE_TEXT_BELOW);
$p->text("EAN-13\n");
$p->barcode('4006381333931', Printer::BARCODE_JAN13);
$p->feed();
$p->text("CODE128\n");
$p->barcode('{BEMUPOS-128', Printer::BARCODE_CODE128);
$p->feed();
$p->cut();
finish($p);

$p = job('qr');
$p->text("Scan me\n");
$p->qrCode('https://example.com', Printer::QR_ECLEVEL_L, 4);
$p->cut();
finish($p);

$p = job('raster-image');
$p->setJustification(Printer::JUSTIFY_CENTER);
$p->bitImage($checkerboard);
$p->cut();
finish($p);

$p = job('column-image');
$p->bitImageColumnFormat($checkerboard);
$p->cut();
finish($p);

$p = job('graphics-image');
$p->graphics($checkerboard);
$p->cut();
finish($p);

$p = job('arabic-image');
$p->text("Receipt 1024\n");
$p->bitImage($arabicLine);
$p->cut();
finish($p);
