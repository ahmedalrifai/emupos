# Spike result: Windows SNMP status (task 1.3)

Status: not run · Date: ___ · Run by: ___ · Kit: `spikes/windows-snmp/`

## Question

1. Which SNMP requests (version, community, PDU type, OIDs, timing) does the Windows Standard TCP/IP port monitor send for a queue on 127.0.0.1 with SNMP status enabled?
2. Which responses make the queue show ready, low paper (warning only), paper out, door open and offline?
3. With two queues pointing at 127.0.0.1, can the responder tell them apart (device index, community)?

## Environment

| Item | Value |
|---|---|
| Windows edition, version, build | |
| SNMP Service installed / running before the test | |
| Python / uv version | |
| Wireshark and Npcap versions (if used) | |
| `Get-PrinterPort emupos-spike` (SNMPEnabled, SNMPCommunity, SNMPIndex) | |

## Observations

1. During `create_queue.ps1`: SNMP requests ___; TCP connections to 9100 ___
2. Polling: first request ___ s after creation; interval ___; triggered by opening the queue / printing? ___
3. Requests for the default queue: version ___; community ___; PDU types ___; OIDs in order ___
4. Status matrix:

   | Run | Fake printer | Settings status text | `Get-Printer` PrinterStatus | Test job printed / held | Requests seen |
   |---|---|---|---|---|---|
   | H | not running | | | | |
   | A | silent | | | | |
   | B | nosuch | | | | |
   | C | ready | | | | |
   | D | low-paper | | | | |
   | E | paper-out | | | | |
   | E2 | paper-out, 2 octets | | | | |
   | F | door-open | | | | |
   | G | offline | | | | |

5. Time from changing state to Windows showing it: ___
6. Two queues: queue 2 sends community ___ and index ___; `--index-state 2=paper-out` gave ___; `--community-state back=paper-out` gave ___
7. Port 161: conflict seen? error text ___
8. Wireshark: traffic not in the log (other OIDs, other ports or addresses)? ___
9. Bytes of the `Out-Printer` test job (from `jobs/`): ___
10. Admin rights: did `-SkipAdminCheck` work from a normal PowerShell? ___

## Decision

Objects the responder must answer (task 10.3): ___

| emupos fault | hrDeviceStatus | hrPrinterStatus | hrPrinterDetectedErrorState | Windows shows |
|---|---|---|---|---|
| none | | | | |
| paper-near-end | | | | |
| paper-out | | | | |
| cover-open | | | | |
| offline | | | | |

- Per-queue identification: [ ] device index (`-SNMP`) [ ] community [ ] not possible (spec change needed)
- hrPrinterDetectedErrorState length: [ ] 1 octet [ ] 2 octets

## Impact on specs and tasks

- windows-print-queue spec, "Queue status reflects printer state" (especially "Each queue reports its own printer") and "SNMP status responder": ___
- design.md D7 and the Open Question on SNMP objects: ___
- tasks 10.1 (SNMP settings per port), 10.3, 10.4, 10.5: ___
