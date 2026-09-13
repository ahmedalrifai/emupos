// Print typical jobs with node-thermal-printer (ISC) and ReceiptPrinterEncoder (MIT) to the
// capture server. Neither is an emupos dependency; install them in a scratch directory:
//
//   mkdir /tmp/nodejobs && cd /tmp/nodejobs && npm init -y
//   npm install node-thermal-printer@4.6.1 @point-of-sale/receipt-printer-encoder@3.0.3
//   uv run spikes/printer-capture/capture.py /tmp/captures &
//   NODE_PATH=/tmp/nodejobs/node_modules node spikes/printer-capture/node_jobs.mjs /tmp/nodejobs
//
// Each job is one connection, sent in the order printed.

import net from "node:net";
import { createRequire } from "node:module";
import path from "node:path";

const modules = path.join(process.argv[2] ?? ".", "node_modules");
const require = createRequire(path.join(modules, "noop.js"));
const { ThermalPrinter, PrinterTypes, CharacterSet } = require("node-thermal-printer");
const { PNG } = require("pngjs");
const ReceiptPrinterEncoder = require("@point-of-sale/receipt-printer-encoder");

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function send(bytes) {
  return new Promise((resolve, reject) => {
    const socket = net.connect(9100, "127.0.0.1", () => socket.end(Buffer.from(bytes)));
    socket.on("close", resolve);
    socket.on("error", reject);
  });
}

function checkerboard() {
  const width = 160;
  const height = 64;
  const rgba = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const black = (Math.floor(x / 16) + Math.floor(y / 16)) % 2 === 0;
      const i = (y * width + x) * 4;
      rgba.set(black ? [0, 0, 0, 255] : [255, 255, 255, 255], i);
    }
  }
  return { data: rgba, width, height };
}

function thermalPrinter() {
  return new ThermalPrinter({
    type: PrinterTypes.EPSON,
    interface: "tcp://127.0.0.1:9100",
    characterSet: CharacterSet.PC437_USA,
    width: 48,
  });
}

// --- node-thermal-printer -------------------------------------------------------------------

console.log("node-thermal-printer receipt");
let printer = thermalPrinter();
printer.alignCenter();
printer.setTextDoubleHeight();
printer.println("EMUPOS MARKET");
printer.setTextNormal();
printer.println("12 Example Street");
printer.alignLeft();
printer.drawLine();
printer.tableCustom([
  { text: "Tomatoes", align: "LEFT", width: 0.6 },
  { text: "2", align: "CENTER", width: 0.1 },
  { text: "3.50", align: "RIGHT", width: 0.3 },
]);
printer.bold(true);
printer.leftRight("TOTAL", "7.00");
printer.bold(false);
printer.underline(true);
printer.println("Thank you");
printer.underline(false);
printer.setTextSize(1, 1);
printer.println("2x2");
printer.setTextNormal();
printer.printBarcode("4006381333931", 67);
printer.code128("EMUPOS-128");
printer.printQR("https://example.com", { cellSize: 4, correction: "M", model: 2 });
printer.openCashDrawer();
printer.cut();
await printer.execute();
await sleep(500);

console.log("node-thermal-printer image");
printer = thermalPrinter();
const board = checkerboard();
const png = new PNG({ width: board.width, height: board.height });
png.data = Buffer.from(board.data);
await printer.printImageBuffer(PNG.sync.write(png));
printer.cut();
await printer.execute();
await sleep(500);

// --- ReceiptPrinterEncoder ------------------------------------------------------------------

console.log("receipt-printer-encoder receipt");
let encoder = new ReceiptPrinterEncoder({ language: "esc-pos", printerModel: "epson-tm-t20iii" });
await send(
  encoder
    .initialize()
    .align("center")
    .size(2, 2)
    .line("EMUPOS")
    .size(1, 1)
    .align("left")
    .bold(true)
    .line("Bold")
    .bold(false)
    .underline(true)
    .line("Underline")
    .underline(false)
    .font("B")
    .line("Font B")
    .font("A")
    .rule()
    .barcode("4006381333931", "ean13", 60)
    .qrcode("https://example.com", 2, 4, "m")
    .pulse()
    .cut()
    .encode(),
);
await sleep(500);

console.log("receipt-printer-encoder image");
encoder = new ReceiptPrinterEncoder({ language: "esc-pos", printerModel: "epson-tm-t20iii" });
await send(encoder.initialize().image(checkerboard(), 160, 64, "threshold").cut().encode());
await sleep(500);

console.log("receipt-printer-encoder arabic-codepage");
encoder = new ReceiptPrinterEncoder({ language: "esc-pos", printerModel: "epson-tm-t20iii" });
await send(encoder.initialize().codepage("cp864").line("TOTAL المجموع").cut().encode());
await sleep(500);
