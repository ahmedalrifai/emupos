# Changelog

## [0.4.0](https://github.com/ahmedalrifai/emupos/compare/v0.3.0...v0.4.0) (2026-09-24)


### Features

* **printer:** reply to GS I with the identity in the profile ([#43](https://github.com/ahmedalrifai/emupos/issues/43)) ([727d0fa](https://github.com/ahmedalrifai/emupos/commit/727d0fafdaaec85ea44e1535096e17dc5eab8e3e))
* **scale:** speak the SMA protocol as well as Toledo 8217 ([#44](https://github.com/ahmedalrifai/emupos/issues/44)) ([149adeb](https://github.com/ahmedalrifai/emupos/commit/149adeb65b3c56014c613bbaa03fbaf28b133ac9))
* serve a control page with `emupos run --ui` ([#40](https://github.com/ahmedalrifai/emupos/issues/40)) ([c68bc96](https://github.com/ahmedalrifai/emupos/commit/c68bc969b47856853f26cb8d1e328af8ba7f8c9a))

## [0.3.0](https://github.com/ahmedalrifai/emupos/compare/v0.2.0...v0.3.0) (2026-09-19)


### Features

* **docker:** publish an image that runs the simulator ([#35](https://github.com/ahmedalrifai/emupos/issues/35)) ([fa7c471](https://github.com/ahmedalrifai/emupos/commit/fa7c471592e9a61f2f0a9e86e593fdf83270ad79))
* **printer:** render glyphs for every code page the profiles claim ([#32](https://github.com/ahmedalrifai/emupos/issues/32)) ([11eb0a7](https://github.com/ahmedalrifai/emupos/commit/11eb0a7dc815b93863c42cefc6d51c07ba31d3e2))
* **printer:** simulate ESC i and ESC m cuts, ESC v and ESC u status, and GS T ([#30](https://github.com/ahmedalrifai/emupos/issues/30)) ([3b63202](https://github.com/ahmedalrifai/emupos/commit/3b63202acd46d63857a81e23a28b10bf0433bfff))
* **scanner:** type keyboard scans on the client that requested them ([#33](https://github.com/ahmedalrifai/emupos/issues/33)) ([d381f65](https://github.com/ahmedalrifai/emupos/commit/d381f6513b914463cf36986204fc6673058671e3))


### Bug Fixes

* **cli:** check the shape of a device id before using it ([#39](https://github.com/ahmedalrifai/emupos/issues/39)) ([c383731](https://github.com/ahmedalrifai/emupos/commit/c3837312f2324958c76b0261bc34dd857e7fcb44))
* **linux:** type exact characters with --unicode on X11 ([#28](https://github.com/ahmedalrifai/emupos/issues/28)) ([b811a29](https://github.com/ahmedalrifai/emupos/commit/b811a29972030d2abaf29600a4f475572ec7d120))
* **printer:** stop ESC r and other unrecognised commands printing their parameters ([#29](https://github.com/ahmedalrifai/emupos/issues/29)) ([c742b2a](https://github.com/ahmedalrifai/emupos/commit/c742b2a57bec6bae300c3750f102c43d3379b053))


### Documentation

* add a documentation badge to the README ([#38](https://github.com/ahmedalrifai/emupos/issues/38)) ([b1ed18c](https://github.com/ahmedalrifai/emupos/commit/b1ed18c502a6a11bafd9545d8951463fad8e7b91))
* **changelog:** list what Windows support in 0.2.0 covers ([#16](https://github.com/ahmedalrifai/emupos/issues/16)) ([8fc149a](https://github.com/ahmedalrifai/emupos/commit/8fc149acad7f6fc528f3074794bca0a84c69622e))
* **openspec:** park the serial bridge with its design intact ([#36](https://github.com/ahmedalrifai/emupos/issues/36)) ([b0992cf](https://github.com/ahmedalrifai/emupos/commit/b0992cfc9cdebc45f2f9e4220bb72fa90677e05e))
* restructure the guides and publish them on Read the Docs ([#37](https://github.com/ahmedalrifai/emupos/issues/37)) ([9e45243](https://github.com/ahmedalrifai/emupos/commit/9e452433d1bc114d51262720604e5bfa32299cbc))

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
