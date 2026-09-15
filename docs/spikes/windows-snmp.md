# Spike result: Windows SNMP status (task 1.3)

Status: run, partly answered (paper out and per-queue identification not observed) · Date: 2026-09-15 · Run by: Ahmed Alrifai · Kit: `spikes/windows-snmp/`

## Question

1. Which SNMP requests (version, community, PDU type, OIDs, timing) does the Windows Standard TCP/IP port monitor send for a queue on 127.0.0.1 with SNMP status enabled?
2. Which responses make the queue show ready, low paper (warning only), paper out, door open and offline?
3. With two queues pointing at 127.0.0.1, can the responder tell them apart (device index, community)?

## Environment

| Item | Value |
|---|---|
| Windows edition, version, build | Windows 11 Pro 10.0.26200, physical PC (MS-7C02), Secure Boot on |
| SNMP Service installed / running before the test | Not installed (`Start-Service SNMP`: "Cannot find any service with service name 'SNMP'"); UDP 161 was free |
| Python / uv version | CPython 3.13 via uv 0.7.13 |
| Wireshark and Npcap versions (if used) | Not used; `snmp-log.jsonl` was the only capture |
| `Get-PrinterPort emupos-spike` (SNMPEnabled, SNMPCommunity, SNMPIndex) | True, `public`, 1 (port 127.0.0.1:**9200**, protocol RAW, monitor TCPMON.DLL) |

Deviations from the kit:

- **TCP 9200 instead of 9100.** Port 9100 was held by `lghub_updater.exe` (Logitech G HUB), and its service could not be stopped ("Cannot open LGHUBUpdaterService service"). The fake printer ran with `--tcp-port 9200`, the queue with `-PortNumber 9200`, and the second queue on 9201.
- **Print Spooler was stopped** (StartType Manual). Until it was started, `Add-PrinterDriver` failed with `0x800706d9` and `Get-PrinterPort` with `0x800706ba` ("The spooler service is not reachable"). It was started for the test and stopped again afterwards.
- **"Generic / Text Only" was not installed**; `create_queue.ps1` installed it with `Add-PrinterDriver` once the Spooler ran.
- Log times below are UTC; the PC's clock was UTC+2. `notes.txt` has two lines "stopped the Windows SNMP Service" that were pasted without editing; the service does not exist on this PC.

## Observations

1. During `create_queue.ps1`: SNMP requests immediately (logged 15:01:58 and 15:18:45 for the two creations): GETNEXT `1.3.6.1.4.1.2699.1.2`, then GET `sysDescr.0`, then GET of the three status objects for index 1. No TCP connection to the print port until a job was sent.
2. Polling, all from one UDP source port per Spooler run (58312, later 55955):
   - Discovery pair (GETNEXT `1.3.6.1.4.1.2699.1.2` + GET `sysDescr.0`) every 10 minutes (15:18:45, 15:28:45 … 16:28:45), often sent twice 1 s apart. `2699.1.2` is under the Printer Working Group enterprise number; the kit answered noSuchName and Windows carried on.
   - Status GET every 10 minutes while the printer is healthy (15:49:39, 15:59:40, 16:09:40, 16:21:37, 16:27:07 → 16:37:07), and sometimes right around a job (16:11:37, 15:39:49).
   - No reply (run A): the same GET 3 times 10 s apart, repeated every 60 s.
   - noSuchName reply (run B): every 60 s.
   - Error state reported (runs F and G): again after 60 s, then every 30 s.
3. Requests for the default queue: version **v1 only** (no v2c seen); community `public` (the port's `-SNMPCommunity`); PDU types GETNEXT and GET; status OIDs in one GET, in this order: `1.3.6.1.2.1.25.3.2.1.5.1` (hrDeviceStatus), `1.3.6.1.2.1.25.3.5.1.1.1` (hrPrinterStatus), `1.3.6.1.2.1.25.3.5.1.2.1` (hrPrinterDetectedErrorState). sysObjectID, sysUpTime, hrDeviceType and hrDeviceDescr were never requested.
4. Status matrix (each run waited 2 minutes, printed one `Out-Printer` job, waited 15 s, then read `Get-Printer` and Settings):

   | Run | Fake printer | Settings status text | `Get-Printer` PrinterStatus | Test job printed / held | Requests seen |
   |---|---|---|---|---|---|
   | H | not running | Offline | Normal (job "Printing, Retained") | retried; delivered at 15:32:38 when run A started listening | none (nothing listening) |
   | A | silent | Offline | Offline | held | status GET ×3 every 60 s, unanswered |
   | B | nosuch | Offline | Offline | held (A and B jobs) | status GET every 60 s, noSuchName |
   | C | ready | Offline in the first C run (15:39:58), Idle in a repeat (16:06:52) | Normal | printed; held A and B jobs printed 0.1 s after the first ready reply (15:39:49) | status GET answered 2/3/00 |
   | D | low-paper | Idle | Normal | printed (16:11:37) | status GET at 16:09:40 and 16:11:37 answered 3/3/80 |
   | E | paper-out | Idle | Normal | printed (16:14:28) | **none**: no poll between 16:12:28 and 16:15:37, so paper out was never reported |
   | E2 | paper-out, 2 octets | Idle | Normal | printed (16:17:37) | discovery pair only (16:18:45); **no status GET** |
   | F | door-open | Door open | DoorOpen | held | status GET at 16:21:37 answered 5/1/08, then every 30 to 60 s |
   | G | offline | Offline | Offline | held | status GET at 16:24:07 answered 5/1/02, then every 30 s |

   Back to ready (step 2.5): the status GET at 16:27:07 answered 2/3/00, and the held F and G jobs printed at once.

5. Time from changing state to Windows showing it: from a healthy state, until the next 10-minute status poll (up to 10 minutes; runs E and E2 fell entirely between polls). From an error state, within 30 to 60 s. Settings did not always refresh: the first run C showed Offline in Settings while `Get-Printer` already said Normal.
6. Two queues: queue 2 (`-DeviceIndex 2 -Community back`, port 9201) sent community **`back`** and index **2** in its first status GET at 16:30:43 (`…25.3.2.1.5.2`, `…25.3.5.1.1.2`, `…25.3.5.1.2.2`, v1). The fake printer was still answering index 1 only, so it replied noSuchName. Queue 2 then sent no further request before the log ends at 16:37:07, unlike queue 1 in run B, which re-polled every 60 s. `--index-state 2=paper-out` gave Idle / Idle (both Normal) and `--community-state back=paper-out` gave Idle / Idle, but neither run received a request, and paper out was not observable anyway (row E). **Not observed.**
7. Port 161: no conflict. The Windows SNMP Service is not installed on this PC.
8. Wireshark: not used.
9. Bytes of the `Out-Printer` test job: `0d 0a 0a 0a 0a 0a 0a` + 10 spaces + `emupos spike run H` + `0c` (36 bytes). No ESC/POS commands; the "Generic / Text Only" driver renders text with CR LF line ends, a top margin of line feeds, a left margin of spaces and a form feed at the end. Notepad jobs (step 2.5) had the same shape with a 7-space margin. The Arabic line `المجموع 4.75` arrived as `....... 4.75` (one `.` per Arabic character), and the empty line in `receipt.txt` was not printed.
10. Admin rights: `-SkipAdminCheck` not tried.
11. Cleanup: `remove_queue.ps1` removed both queues, but `Remove-PrinterPort` failed for both ports with `0x800700aa` ("The specified port is in use by one or more printers"), although neither queue had jobs left (`JobCount 0` at 18:32 and 18:35 local). `Restart-Service Spooler` followed by `Remove-PrinterPort` removed both.

## Decision

Objects the responder must answer (task 10.3), SNMP v1 (keep v2c as the spec says; Windows did not use it):

- GETNEXT `1.3.6.1.4.1.2699.1.2`: a noSuchName (v1) or endOfMibView (v2c) reply is enough.
- GET `sysDescr.0` (`1.3.6.1.2.1.1.1.0`).
- GET `hrDeviceStatus.N`, `hrPrinterStatus.N`, `hrPrinterDetectedErrorState.N` in one request, where N is the port's SNMP index.

| emupos fault | hrDeviceStatus | hrPrinterStatus | hrPrinterDetectedErrorState | Windows shows |
|---|---|---|---|---|
| none | running(2) | idle(3) | `00` | Idle (observed, run C) |
| paper-near-end | warning(3) | idle(3) | `80` (lowPaper) | Idle; no warning, jobs print (observed, run D) |
| paper-out | down(5) | other(1) | `40` (noPaper) | not observed (runs E and E2 got no status poll); expected to be an error like door open, to confirm in task 10.5 |
| cover-open | down(5) | other(1) | `08` (doorOpen) | Door open; `Get-Printer` DoorOpen; jobs held (observed, run F) |
| offline | down(5) | other(1) | `02` (offline) | Offline; jobs held (observed, run G) |

No reply and noSuchName both show Offline and hold jobs (runs A and B).

- Per-queue identification: [x] device index (`-SNMP`) [ ] community [ ] not possible (spec change needed). Reason: each port's status GET carries its own index (and its own community), so the responder can pick the printer by index; community would work too. Not yet verified end to end, because the two-queue runs got no poll after the first request.
- hrPrinterDetectedErrorState length: [x] 1 octet [ ] 2 octets. Reason: Windows decoded the 1-octet values `08` and `02`; the 2-octet run was never polled.

## Impact on specs and tasks

- windows-print-queue spec, "Queue status reflects printer state": nothing contradicted. `paper-near-end` as a low-paper warning matches (Windows shows nothing and keeps printing). "Each queue reports its own printer" stays feasible, since requests carry the port's index and community; end-to-end confirmation moves to 10.5. The documentation must say that Windows polls a healthy printer about every 10 minutes, so a new fault can take up to 10 minutes to appear in Windows, while clearing a fault shows within a minute. "SNMP status responder": Windows used v1 GET and GETNEXT with the objects above. "One-way printing limitation": also document that ordinary applications (Notepad, `Out-Printer`) print through "Generic / Text Only" as plain text, and characters outside its code page such as Arabic become `.`.
- design.md D7 and the Open Question on SNMP objects: the object list and value mapping above answer the question except paper out. D7's "passes the application's bytes through unchanged" holds only for RAW jobs; GDI printing is rendered to plain text. RAW submission was not exercised here.
- tasks 10.1 (SNMP settings per port): give each printer's port a distinct `-SNMP` index; the responder has to answer that index from the moment the port exists, because queue 2 stopped polling after one noSuchName. Detect a stopped Spooler (`0x800706ba`) with a clear fix, and install "Generic / Text Only" when missing. 10.2: `Remove-PrinterPort` can fail with `0x800700aa` right after the queue is removed; restart the Spooler (or retry) before deleting the port. 10.3: the objects above. 10.4: the SNMP Service may be absent entirely. 10.5: re-check paper out with a poll inside the window (start from door open so Windows polls every 30 s), re-check two queues end to end, and submit a RAW job. 12.6 doctor: name the process holding a configured TCP port (here `lghub_updater.exe` on 9100) and report a stopped Spooler when a queue exists.
