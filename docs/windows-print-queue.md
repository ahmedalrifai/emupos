# Windows: printing through a print queue

Some POS applications print to a Windows printer by name instead of to an IP address. `emupos setup print-queue` creates a Windows print queue that sends every job to a simulated printer, so those applications can print to emupos.

A print queue is **one-way**: see [Status replies](#status-replies-do-not-come-back). Connect the POS to the printer's TCP port directly whenever you can.

## Create the queue

You need:

- `emupos run` running, with a printer that has a `tcp` connection (`connections: [ { tcp: { port: 9100 } } ]`);
- permission to manage printers. Windows decides this per account: on a test PC with an administrator account and UAC on, a normal terminal could create and remove queues. If Windows refuses, emupos says so; then open the terminal with **Run as administrator**;
- the Print Spooler service running (it is on most machines).

```powershell
emupos setup print-queue --device front
```

`--device` can be left out when the simulator has one printer. This creates:

- a Standard TCP/IP printer port `emupos-front` that sends raw data to `127.0.0.1:9100`, with SNMP status on (community `public`, device index 9100: the printer's TCP port);
- a print queue `emupos-front` using the built-in "Generic / Text Only" driver, which is installed first if it is missing.

Running the command again leaves one queue and one port. If the printer's TCP port changed in `emupos.yaml`, run it again after restarting `emupos run` and the queue follows the new port.

## What arrives at the printer

- **Raw jobs pass through unchanged.** An application that submits its ESC/POS bytes as a raw job gets them to emupos byte for byte, over one TCP connection per job: receipts, cuts and drawer kicks work as they do over TCP.
- **Text from ordinary applications is converted.** Notepad or `Out-Printer` print through the Generic / Text Only driver, which sends plain text: blank lines at the top, a margin of spaces before each line, CR LF line ends and a form feed at the end. Empty lines can be dropped. Characters outside the driver's code page, such as Arabic, become `.`. emupos prints that text and reports the form feed as an unknown command.

## Status replies do not come back

A print queue only sends data to the printer. A POS printing through the queue receives **no reply**: no `DLE EOT` or `GS r` status and no Automatic Status Back. To test paper out, cover open or the drawer sensor, connect the POS to the printer's TCP port (or serial connection) directly. `emupos doctor` repeats this when an `emupos-` queue exists.

## Queue status in Windows

While `emupos run` runs, it answers the SNMP status requests Windows sends for the queue, on UDP port 161 of `127.0.0.1`. Windows then shows the printer's faults:

| Fault in emupos | Windows shows | Jobs |
|---|---|---|
| none | Idle (ready) | printed |
| `paper-near-end` | Idle (Windows ignores the low-paper warning) | printed |
| `paper-out` | Out of paper | held until the fault clears |
| `cover-open` | Door open | held until the fault clears |
| `offline` | Offline | held until the fault clears |
| `emupos run` is not running | Offline | wait in the queue |

**Windows is slow to notice a new fault.** It asks a printer without faults for its status only about every 10 minutes, so a fault you set can take up to 10 minutes to appear on the queue. While a fault is shown, Windows asks every 30 to 60 seconds, so clearing it shows within a minute. A job sent to a new queue before Windows has asked for its status prints even when the printer has a fault: wait until the queue shows the fault before testing held jobs.

Each queue's port uses the printer's TCP port as its SNMP device index, so with several printers every queue shows its own printer's faults.

### UDP port 161 is in use

If another program holds UDP port 161, `emupos run` keeps all devices running but prints an error, and queues show no printer status. The usual cause is the Windows "SNMP Service" (not installed by default). Stop it in a PowerShell opened with "Run as administrator":

```powershell
Stop-Service SNMP
Set-Service SNMP -StartupType Disabled
```

`emupos doctor` names the program holding the port. The check fails when an `emupos-` queue exists and is a warning otherwise.

## Remove the queue

```powershell
emupos setup print-queue --device front --remove
```

This deletes the queue and its port. It does not need `emupos run`, and needs the same permission as creating the queue. Windows can keep a port "in use" for a moment after its queue is deleted; emupos retries, and if the port is still held it restarts the Print Spooler, which briefly interrupts other printing on the machine.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Run as administrator" error | Open the terminal with right-click → Run as administrator and run the command again. |
| The Print Spooler is not running | `Start-Service Spooler`. If it is disabled, first `Set-Service Spooler -StartupType Automatic`. |
| The queue shows Offline while `emupos run` runs | UDP port 161 is taken (above), or Windows has not asked again yet: wait a minute. |
| `emupos run` cannot listen on the printer's port | Another program holds it; `emupos doctor` names it (Logitech G HUB's `lghub_updater.exe` uses 9100, for example). Choose another port in `emupos.yaml` and run `emupos setup print-queue` again. |
| The queue exists but the printer has no `tcp` connection | Add `connections: [ { tcp: { port: 9100 } } ]` to the printer, restart `emupos run`, and run the setup again. |
