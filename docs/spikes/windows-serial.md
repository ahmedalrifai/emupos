# Spike result: Windows serial (task 1.1)

Status: run; driver blocked with Secure Boot on, backends compared in the 2026-09-16 follow-up · Date: 2026-09-15 · Run by: Ahmed Alrifai · Kit: `spikes/windows-serial/`

## Question

1. Does the signed com0com 3.0.0.0 driver install and load with Secure Boot on, or is it blocked (Code 52)?
2. Against a com0com pair, is serialx (asyncio) reliable over 100 open/close/write cycles, including writes while the peer is closed, or should pyserial in a worker thread be the default COM backend?
3. Can com0com be installed on a GitHub-hosted Windows runner?

## Environment

| Item | Value |
|---|---|
| Windows edition, version, build | Windows 11 Pro 10.0.26200 |
| Physical PC or VM (which hypervisor) | Physical PC (MS-7C02 motherboard), x64 |
| Secure Boot (`Confirm-SecureBootUEFI`) | True (before the install and again after the driver was blocked) |
| Python / uv version | CPython 3.13 via uv 0.7.13 |
| com0com zip SHA-256 | `6E5D4359865277430D4AE88C73FB7E648A0ED8E81AEA5002478179CFCB0BB0E1` (matches the kit) |
| Installer signature (status, signer, certificate dates) | `Setup_com0com_v3.0.0.0_W7_x64_signed.exe`: Valid, "Signature verified."; signer CN=CyberCircuits, O=CyberCircuits, Auckland, NZ; certificate 2016-01-04 to 2018-01-27 |
| `com0com.sys` version (Driver Details) | 3.0.0.0 (`Win32_PnPSignedDriver`: IsSigned False, no signer) |
| `setupc list` (default run) | `CNCA0 PortName=COM#` / `CNCB0 PortName=COM#`; after `change … RealPortName=COM5/COM6` still no RealPortName listed |
| `setupc list` (emu run) | not run (driver blocked) |
| serialx / pyserial (from the result JSON) | not run (no port pair) |

## Observations

1. Install prompts and warnings: none (confirmed in the recheck).
2. Driver state (`Get-PnpDevice`): "com0com - bus for serial port pair emulator 0 (COM# <-> COM#)", class CNCPorts, Status **Error**, ConfigManagerErrorCode **CM_PROB_UNSIGNED_DRIVER** (Code 52). Device Manager: "Windows cannot verify the digital signature for the drivers required for this device … (Code 52)". Code Integrity log, event 3004 at 18:46:23 local: "Windows is unable to verify the image integrity of the file \Device\HarddiskVolume4\Windows\System32\drivers\com0com.sys because file hash could not be found on the system."
3. Ports listed under "Ports (COM & LPT)" and in `GetPortNames()`: only `COM1`, before and after. No com0com ports were created.
4. Results (from `result-*.json`): not run. With the driver blocked there was no COM5/COM6 pair, so steps 3.6 and 3.7 were skipped.

   | | serialx default | pyserial default | serialx emu | pyserial emu |
   |---|---|---|---|---|
   | all rows | not run | not run | not run | not run |

5. Did the script hang, crash or need Ctrl+C? Not run.
6. Errors or tracebacks printed: none from the spike script.
7. GitHub-hosted runner: untested.
8. Uninstall clean: yes. `setupc remove 0` printed "Disabled root\com0com" and "Removed root\com0com"; `Get-PnpDevice` afterwards found no com0com devices.
9. Anything else: the installer's Authenticode signature is valid, but the kernel driver is not accepted. The certificate is a plain code-signing certificate from 2016 to 2018, and Windows 10 1607 and later with Secure Boot on only load new kernel drivers signed through Microsoft's portal (attestation or WHQL), which fits "file hash could not be found".

## Decision

- [x] serialx is the default COM backend; pyserial-in-a-thread stays as the fallback
- [ ] pyserial in a worker thread is the default
- [x] emupos docs must tell users to set `EmuOverrun=yes,EmuBR=yes` on the pair
- [ ] Serial integration tests run on GitHub-hosted Windows runners / locally only

The two ticked boxes come from the follow-up run below, not from this one. Reason at the time: none of these could be decided from this run. com0com 3.0.0.0 does not load on Windows 11 with Secure Boot on, so no pair existed to compare the backends against. The backend choice needs a working COM pair: a Microsoft-signed virtual serial port driver, a machine with Secure Boot off, or two USB serial adapters joined by a null-modem cable.

## Follow-up: the backend comparison (2026-09-16)

Same PC, Secure Boot turned off in the firmware for one session, com0com 3.0.0.0 reinstalled and a pair created with `setupc install PortName=COM# PortName=COM#` and `change … RealPortName=COM5/COM6`.

- The driver loads with Secure Boot off: both ports and the bus show `Status OK`, `CM_PROB_NONE`, and `COM5`/`COM6` appear under Ports (COM & LPT).
- `spikes/windows-serial/serial_spike.py COM5 COM6`, 100 cycles per backend, in both com0com modes: **no cycle failed in any of the four runs** (`result-serialx-default.json`, `result-pyserial-default.json`, `result-serialx-emu.json`, `result-pyserial-emu.json`).

| | serialx default | pyserial default | serialx emu | pyserial emu |
|---|---|---|---|---|
| cycles failed | 0 of 100 | 0 of 100 | 0 of 100 | 0 of 100 |
| open, median | 1.45 ms | 0.50 ms | 1.44 ms | 0.56 ms |
| latency, median (both ways) | 14.9 / 15.5 ms | 0.38 / 0.36 ms | 295 ms | 279 ms |
| write while the peer is closed | blocked, TimeoutError after 5 s | blocked, SerialTimeoutException after 2 s | accepted at once | accepted at once |
| stale bytes after reopen | none | none | 15 of 100 | 74 of 100 |
| client at 7E1 against a sim at 8N1 | top bit stripped both ways | same | same | same |
| elapsed | 558 s | 253 s | 171 s | 165 s |

- **serialx stays the default.** Neither backend lost data, so the tie-breaker is that serialx speaks asyncio directly, while pyserial needs a worker thread bridged to streams.
- **serialx reads about 15 ms later than pyserial.** Its Windows transport sets a 10 ms inter-byte timeout, so a read returns once the incoming bytes stop. For POS replies (a weight, a status byte) this is well inside what real hardware takes.
- **`EmuOverrun=yes,EmuBR=yes` matters.** With com0com's defaults, writing while the other end is closed blocks the writer for seconds. With `EmuOverrun` the write is accepted and dropped, as a real cable behaves; `EmuBR` paces bytes at the baud rate, which is where the 280 ms latency for 256 bytes comes from. The cost is stale bytes turning up after the peer reopens. `docs/windows-serial.md` recommends both.
- The GitHub-hosted runner question stays untested.

## Impact on specs and tasks

- design.md D3 ("COM port (Windows)" row), Risks (Code 52) and Open Questions: the Code 52 risk is confirmed on a current Windows 11 build with Secure Boot on, not just "some machines". The D3 row names serialx, with the comparison above behind it, and the Open Question is closed; the GitHub-runner question is moot for com0com 3.0.0.0 wherever Secure Boot is on.
- device-connections spec, "Existing serial ports": the Windows scenarios assume a working com0com pair, which a default Windows 11 machine with Secure Boot cannot load. Opening an existing COM port stays valid (real ports, USB adapters or another virtual port driver); the missing-port message should not present com0com as the only way.
- pyproject.toml win32 dependency: `serialx` stays, confirmed by the follow-up run.
- tasks 4.4: keep it as an existing-port transport with no assumption about which driver provides the port. 12.6 doctor: detect a com0com device with `CM_PROB_UNSIGNED_DRIVER` and explain that Secure Boot blocks this driver. 13.2 `docs/windows-serial.md`: state that com0com 3.0.0.0 is blocked with Secure Boot on (Code 52), and list the options: Secure Boot off, a signed virtual serial port driver, or real serial hardware.
