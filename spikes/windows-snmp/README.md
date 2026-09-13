# Windows SNMP spike (task 1.3)

**Question.** A Windows queue on a "Standard TCP/IP" port with SNMP status enabled asks the printer over SNMP (UDP 161) whether it is ready. Which requests does Windows send, which answers make the queue show ready, low paper, paper out, door open and offline, and can two queues that both point at 127.0.0.1 be told apart?

Record everything in `docs/spikes/windows-snmp.md`.

## Files

| File | What it does |
|---|---|
| `snmp_spike.py` | Fake printer on 127.0.0.1: SNMP v1/v2c GET/GETNEXT on UDP 161 and a raw print sink on TCP 9100. Logs every request and reply to `snmp-log.jsonl` and saves jobs as spaced hex in `jobs/`. No third-party packages. |
| `create_queue.ps1` | Creates port and queue `emupos-spike`: 127.0.0.1:9100, SNMP on (community `public`, device index 1), driver "Generic / Text Only". |
| `remove_queue.ps1` | Removes them again. |

`snmp_spike.py` modes:

| Flag | Replies |
|---|---|
| `--mode silent` | never replies |
| `--mode nosuch` | GET: noSuchObject (v2c) or noSuchName (v1); GETNEXT: endOfMibView |
| `--mode printer --state STATE` | answers sysDescr, sysObjectID, sysUpTime, hrDeviceType, hrDeviceDescr, hrDeviceStatus, hrPrinterStatus, hrPrinterDetectedErrorState (index 1), and GETNEXT walks over them |

States follow RFC 3805 section 2.2.13.2 and the RFC 2790 bit numbering:

| `--state` | hrDeviceStatus | hrPrinterStatus | hrPrinterDetectedErrorState |
|---|---|---|---|
| `ready` | running(2) | idle(3) | `00` |
| `low-paper` | warning(3) | idle(3) | `80` (lowPaper, bit 0) |
| `paper-out` | down(5) | other(1) | `40` (noPaper, bit 1) |
| `door-open` | down(5) | other(1) | `08` (doorOpen, bit 4) |
| `offline` | down(5) | other(1) | `02` (offline, bit 6) |

Other options: `--error-octets 2` (send the error state as two bytes), `--index N`, `--index-state N=STATE`, `--community-state NAME=STATE`, `--duration SECONDS`. `--self-test` checks the encoder/decoder without touching the network beyond loopback.

## 0. Before you start

- Optional but useful: [Wireshark](https://www.wireshark.org/) with Npcap installed with **"Support loopback traffic"**. Capture on the *Adapter for loopback traffic capture* with filter `udp.port == 161 || tcp.port == 9100`, and save the capture.
- Check nothing else holds UDP 161. In an **admin PowerShell**:

  ```powershell
  Get-Service SNMP -ErrorAction SilentlyContinue
  Get-NetUDPEndpoint -LocalPort 161 -ErrorAction SilentlyContinue | Select-Object LocalAddress, OwningProcess
  ```

  If the Windows **SNMP Service** is running, note it, then `Stop-Service SNMP` (and `Start-Service SNMP` when you are done).
- `uv run spikes/windows-snmp/snmp_spike.py --self-test` should end with `SELF-TEST PASSED`.

## 1. Start the fake printer

In a normal terminal, from the repository root:

```powershell
uv run spikes/windows-snmp/snmp_spike.py --mode printer --state ready
```

Leave it running; every request is printed and logged. If Windows Firewall asks about Python, note it (loopback traffic does not need an exception; *Cancel* is fine).

## 2. Create the queue

In an **admin PowerShell** at the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File spikes\windows-snmp\create_queue.ps1
```

Watch the fake printer's output while this runs: note any SNMP requests and TCP connections during port creation.

## 3. Watch the status

- *Settings > Bluetooth & devices > Printers & scanners > emupos-spike*: the status text.
- `Get-Printer -Name emupos-spike | Format-List Name, PrinterStatus, JobCount`
- Print a test job: `"Hello" | Out-Printer -Name emupos-spike`, then check `Get-PrintJob -PrinterName emupos-spike` and the new file in `spikes\windows-snmp\jobs\`.

Windows polls on its own schedule. After each change wait 2 minutes, note when the first request arrived (the log has timestamps), and whether opening the queue window or printing triggers a request.

## 4. Run the matrix

For each row: stop the fake printer (Ctrl+C), start it with the new flags, wait 2 minutes, print one test job, and fill in the row in the template.

| Run | Command |
|---|---|
| H | fake printer not running at all |
| A | `uv run spikes/windows-snmp/snmp_spike.py --mode silent` |
| B | `uv run spikes/windows-snmp/snmp_spike.py --mode nosuch` |
| C | `uv run spikes/windows-snmp/snmp_spike.py --mode printer --state ready` |
| D | `... --mode printer --state low-paper` |
| E | `... --mode printer --state paper-out` |
| E2 | `... --mode printer --state paper-out --error-octets 2` |
| F | `... --mode printer --state door-open` |
| G | `... --mode printer --state offline` |

## 5. Two queues on 127.0.0.1

Can the SNMP responder tell which queue is asking? SNMP carries no TCP port, so only the community string and the device index configured on each port could identify the queue.

1. Create a second queue on port 9101 with index 2 and community `back` (admin PowerShell):

   ```powershell
   powershell -ExecutionPolicy Bypass -File spikes\windows-snmp\create_queue.ps1 -Name emupos-spike2 -PortNumber 9101 -DeviceIndex 2 -Community back
   ```

2. In a second terminal, give queue 2 a print sink (its SNMP port is only there to avoid a clash):

   ```powershell
   uv run spikes/windows-snmp/snmp_spike.py --port 1162 --tcp-port 9101 --log spikes/windows-snmp/snmp-log-sink2.jsonl --jobs spikes/windows-snmp/jobs2
   ```

3. Look at the log: which community and which OID index does each queue send?
4. By index: `uv run spikes/windows-snmp/snmp_spike.py --state ready --index-state 2=paper-out`. Does only `emupos-spike2` show paper out?
5. By community: `uv run spikes/windows-snmp/snmp_spike.py --state ready --community-state back=paper-out`. Does only `emupos-spike2` show paper out?

## 6. Clean up

```powershell
powershell -ExecutionPolicy Bypass -File spikes\windows-snmp\remove_queue.ps1
powershell -ExecutionPolicy Bypass -File spikes\windows-snmp\remove_queue.ps1 -Name emupos-spike2
```

Restart the SNMP Service if you stopped it. The scripts refuse to run without administrator rights; Microsoft's documentation says `Add-PrinterPort` does not need them, so if you want, try `-SkipAdminCheck` from a normal PowerShell and record what fails.

## Send back

`docs/spikes/windows-snmp.md` filled in, `snmp-log.jsonl` (and `snmp-log-sink2.jsonl`), the `jobs` folders, and the Wireshark capture if you made one.
