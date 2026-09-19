# emupos documentation

New to emupos? Start with the [main README](../README.md): what emupos is, its two sides, installation and a five-minute quickstart.

## Using emupos

| Guide | What it covers |
|---|---|
| [configuration.md](configuration.md) | Every key of `emupos.yaml` and the device profile format, with a complete example. |
| [cli.md](cli.md) | Every `emupos` command and option, generated from the CLI itself. |
| [automation.md](automation.md) | Driving emupos from automated tests and CI through the control API, with curl, Python, Node.js and GitHub Actions examples. |

## Setting up your operating system

| Guide | What it covers |
|---|---|
| [macos-accessibility.md](macos-accessibility.md) | Allowing keyboard-mode scans on macOS (the Accessibility permission). |
| [linux-x11.md](linux-x11.md) | Keyboard-mode scans on Linux: X11, libXtst, Wayland and headless machines. |
| [docker.md](docker.md) | Running the simulator from the published image: ports, your own configuration, and what belongs on your own machine. |
| [windows-keyboard.md](windows-keyboard.md) | Keyboard-mode scans on Windows: focus, privilege levels, layouts and `--unicode`. |
| [windows-serial.md](windows-serial.md) | Serial devices on Windows: COM port pairs, and com0com with Secure Boot. |
| [windows-print-queue.md](windows-print-queue.md) | Printing through a Windows print queue, queue status, and its one-way limit. |

## Protocols

| Guide | What it covers |
|---|---|
| [protocols/escpos-status.md](protocols/escpos-status.md) | The printer's status bytes (`DLE EOT`, `GS r`, Automatic Status Back), the cash drawer sensor, and what happens to each ESC/POS command. |
| [protocols/toledo8217.md](protocols/toledo8217.md) | The Toledo 8217 scale protocol: framing, weight and status replies, the echo probe, with example dialogues. |

## For contributors and maintainers

| Document | What it covers |
|---|---|
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Development setup, code rules, adding a device profile or protocol. |
| [../SECURITY.md](../SECURITY.md) | Reporting vulnerabilities, and the threat model of the local control API. |
| [keyboard-scanning-checklist.md](keyboard-scanning-checklist.md) | The manual checklist for keyboard-mode scanning, run before releases that touch it. |
| [api/openapi-v1.json](api/openapi-v1.json) | The recorded `/api/v1` contract that CI compares the API against. |
| [spikes/](spikes/) | Records of maintainer experiments (Windows serial, keyboard wedge, Windows SNMP). They are working notes, not user guides. |
