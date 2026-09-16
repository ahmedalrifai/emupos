# Changelog

## [0.2.0](https://github.com/ahmedalrifai/emupos/compare/v0.1.2...v0.2.0) (2026-09-16)


### Features

Windows support, all from [#14](https://github.com/ahmedalrifai/emupos/pull/14) ([40de23e](https://github.com/ahmedalrifai/emupos/commit/40de23e31eb30a9d9678e6f34f40219d21a0808b)):

* **windows:** open existing COM ports through serialx (`serial: { port: COM5 }`); a missing port stops startup with a message naming the port, the device, com0com and `emupos doctor`
* **windows:** keyboard-mode scans type with `SendInput`, carrying US virtual-key codes and their scan codes, or exact characters with `--unicode`
* **windows:** `emupos setup print-queue` creates and removes a Standard TCP/IP port and an `emupos-<device id>` queue on the Generic / Text Only driver, and `--remove` works with the simulator stopped
* **windows:** `emupos run` answers the print queue's SNMP status polls on `127.0.0.1:161`, so Windows shows paper out, door open and offline; it keeps every device running when the port is taken
* **windows:** `emupos doctor` checks COM ports and com0com (including a driver blocked by Secure Boot), the Print Spooler and existing queues, UDP port 161, and names the program holding a busy TCP port


### Documentation

* setup guides for Windows: [serial devices](docs/windows-serial.md), [keyboard scans](docs/windows-keyboard.md) and [print queues](docs/windows-print-queue.md), with the one-way limitation of a print queue and its status delay

## [0.1.2](https://github.com/ahmedalrifai/emupos/compare/v0.1.1...v0.1.2) (2026-09-14)


### Bug Fixes

* **printer:** accept the paper type commands Epson's Mac driver sends ([#12](https://github.com/ahmedalrifai/emupos/issues/12)) ([066cd69](https://github.com/ahmedalrifai/emupos/commit/066cd695ab0a91aae19cc80ae91cf895b800d4f4))


### Documentation

* add a code of conduct ([#9](https://github.com/ahmedalrifai/emupos/issues/9)) ([a8b5e38](https://github.com/ahmedalrifai/emupos/commit/a8b5e38cfa6565f95d52b2759883c8691721c2b8))

## [0.1.1](https://github.com/ahmedalrifai/emupos/compare/v0.1.0...v0.1.1) (2026-09-14)


### Bug Fixes

* **cli:** cancel a keyboard scan while the terminal that ran it has focus ([#6](https://github.com/ahmedalrifai/emupos/issues/6)) ([ded9de1](https://github.com/ahmedalrifai/emupos/commit/ded9de19cff2e3473a1b9d44463fc9892a743810))


### Documentation

* **openspec:** record the 0.1.0 release as verified ([#5](https://github.com/ahmedalrifai/emupos/issues/5)) ([246e7bd](https://github.com/ahmedalrifai/emupos/commit/246e7bd8321da5792562638b2055284daefd34f2))

## 0.1.0 (2026-09-13)


### Features

* bootstrap emupos v0.1 (printer, drawer, scale, scanner, CLI, API) ([#1](https://github.com/ahmedalrifai/emupos/issues/1)) ([b985398](https://github.com/ahmedalrifai/emupos/commit/b9853985026fff48dfc20e4d40087e5fa4669026))
