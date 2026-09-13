# Spike result: Windows serial (task 1.1)

Status: not run · Date: ___ · Run by: ___ · Kit: `spikes/windows-serial/`

## Question

1. Does the signed com0com 3.0.0.0 driver install and load with Secure Boot on, or is it blocked (Code 52)?
2. Against a com0com pair, is serialx (asyncio) reliable over 100 open/close/write cycles, including writes while the peer is closed, or should pyserial in a worker thread be the default COM backend?
3. Can com0com be installed on a GitHub-hosted Windows runner?

## Environment

| Item | Value |
|---|---|
| Windows edition, version, build | |
| Physical PC or VM (which hypervisor) | |
| Secure Boot (`Confirm-SecureBootUEFI`) | |
| Python / uv version | |
| com0com zip SHA-256 | |
| Installer signature (status, signer, certificate dates) | |
| `com0com.sys` version (Driver Details) | |
| `setupc list` (default run) | |
| `setupc list` (emu run) | |
| serialx / pyserial (from the result JSON) | |

## Observations

1. Install prompts and warnings: ___
2. Driver state (`Get-PnpDevice`: Status, ConfigManagerErrorCode): ___
3. Ports listed under "Ports (COM & LPT)" and in `GetPortNames()`: ___
4. Results (from `result-*.json`):

   | | serialx default | pyserial default | serialx emu | pyserial emu |
   |---|---|---|---|---|
   | cycles failed / 100 | | | | |
   | failures by step | | | | |
   | open ms (median / p95) | | | | |
   | round trip client→sim ms (median / p95) | | | | |
   | round trip sim→client ms (median / p95) | | | | |
   | write with client closed (accepted / blocked / error) | | | | |
   | stale bytes after reopen | | | | |
   | client 7E1 vs sim 8N1 / sim 7E1 | | | | |
   | threads alive at end | | | | |
   | elapsed s | | | | |

5. Did the script hang, crash or need Ctrl+C? ___
6. Errors or tracebacks printed (paste): ___
7. GitHub-hosted runner: installs? Yes / No / untested. Notes: ___
8. Uninstall clean (no hidden com0com devices left)? ___
9. Anything else: ___

## Decision

- [ ] serialx is the default COM backend; pyserial-in-a-thread stays as the fallback
- [ ] pyserial in a worker thread is the default
- [ ] emupos docs must tell users to set `EmuOverrun=yes,EmuBR=yes` on the pair
- [ ] Serial integration tests run on GitHub-hosted Windows runners / locally only

Reason: ___

## Impact on specs and tasks

- design.md D3 ("COM port (Windows)" row), Risks (Code 52) and Open Questions: ___
- device-connections spec, "Existing serial ports" (reconnects, stale data): ___
- pyproject.toml win32 dependency (`serialx` or `pyserial`): ___
- tasks 4.4, 12.6 (doctor: Code 52 and pair settings), 13.2 (`docs/windows-serial.md`): ___
