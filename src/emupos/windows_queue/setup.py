"""Creating and removing the Windows print queue of a simulated printer (design D7).

Each script runs in Windows PowerShell with the PrintManagement cmdlets and prints one JSON object:
`{"ok": true, "notes": [...]}`, or `{"ok": false, "step": ..., "message": ..., "error_id": ...}`
where `error_id` carries the HRESULT, e.g. `HRESULT 0x80070005,Add-PrinterPort`.
"""

import json
import subprocess
from base64 import b64encode
from dataclasses import dataclass, field
from typing import Any

DRIVER = "Generic / Text Only"
POWERSHELL_TIMEOUT_SECONDS = 120  # a Print Spooler restart can take a while


def queue_name(device_id: str) -> str:
    return f"emupos-{device_id}"


class QueueSetupError(Exception):
    def __init__(self, message: str, fix: str) -> None:
        super().__init__(message)
        self.message = message
        self.fix = fix


@dataclass(frozen=True, slots=True)
class Outcome:
    changed: bool
    notes: list[str] = field(default_factory=list[str])


_PRELUDE = r"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$notes = New-Object System.Collections.ArrayList
function Emit($result) { $result | ConvertTo-Json -Compress; exit 0 }
function Fail($step, $err) {
    Emit @{ ok = $false; step = $step; message = $err.Exception.Message; error_id = "$($err.FullyQualifiedErrorId)" }
}
$spooler = Get-Service -Name Spooler -ErrorAction SilentlyContinue
if ($null -eq $spooler -or $spooler.Status -ne 'Running') {
    Emit @{ ok = $false; step = 'Print Spooler'; message = 'the Print Spooler service is not running'; error_id = 'spooler_stopped' }
}
function Remove-QueuePort {
    # Right after its queue is deleted the spooler can still hold the port (0x800700aa).
    for ($attempt = 1; $attempt -le 5; $attempt++) {
        try { Remove-PrinterPort -Name $Name; return }
        catch { if ("$($_.FullyQualifiedErrorId)" -notlike '*0x800700aa*') { throw } }
        Start-Sleep -Seconds 1
    }
    Restart-Service -Name Spooler
    [void]$notes.Add('restarted the Print Spooler, which was still holding the old printer port')
    Remove-PrinterPort -Name $Name
}
"""

_CREATE = r"""
$step = 'Get-Printer'
try {
    $queue = Get-Printer -Name $Name -ErrorAction SilentlyContinue
    $port = Get-PrinterPort -Name $Name -ErrorAction SilentlyContinue
    if ($queue -and $port -and $queue.PortName -eq $Name -and $queue.DriverName -eq $Driver -and
        $port.PrinterHostAddress -eq '127.0.0.1' -and $port.PortNumber -eq $Port -and
        $port.SNMPEnabled -and $port.SNMPIndex -eq $Port) {
        Emit @{ ok = $true; changed = $false; notes = @() }
    }
    if (-not (Get-PrinterDriver -Name $Driver -ErrorAction SilentlyContinue)) {
        $step = 'Add-PrinterDriver'
        Add-PrinterDriver -Name $Driver
        [void]$notes.Add("installed the '$Driver' printer driver")
    }
    if ($queue) { $step = 'Remove-Printer'; Remove-Printer -Name $Name }
    if ($port) { $step = 'Remove-PrinterPort'; Remove-QueuePort }
    $step = 'Add-PrinterPort'
    Add-PrinterPort -Name $Name -PrinterHostAddress '127.0.0.1' -PortNumber $Port -SNMP $Port -SNMPCommunity 'public'
    $step = 'Add-Printer'
    try {
        Add-Printer -Name $Name -DriverName $Driver -PortName $Name
    } catch {
        $failure = $_
        try { Remove-QueuePort } catch { [void]$notes.Add("could not delete the printer port '$Name' again: $($_.Exception.Message)") }
        Emit @{ ok = $false; step = $step; message = $failure.Exception.Message; error_id = "$($failure.FullyQualifiedErrorId)"; notes = $notes }
    }
    Emit @{ ok = $true; changed = $true; notes = $notes }
} catch { Fail $step $_ }
"""

_REMOVE = r"""
$step = 'Get-Printer'
try {
    $changed = $false
    if (Get-Printer -Name $Name -ErrorAction SilentlyContinue) {
        $step = 'Remove-Printer'; Remove-Printer -Name $Name; $changed = $true
    }
    if (Get-PrinterPort -Name $Name -ErrorAction SilentlyContinue) {
        $step = 'Remove-PrinterPort'; Remove-QueuePort; $changed = $true
    }
    Emit @{ ok = $true; changed = $changed; notes = $notes }
} catch { Fail $step $_ }
"""

# (HRESULT, message, fix) for the failures a user can fix.
_KNOWN_FAILURES = (
    (
        "0x80070005",
        "Windows refused because this terminal does not have administrator rights",
        'open a terminal with "Run as administrator" and run the command again',
    ),
    (
        "0x800706ba",
        "the Print Spooler service is not reachable",
        'start it in a PowerShell opened with "Run as administrator": `Start-Service Spooler`',
    ),
    (
        "0x800706d9",
        "the Print Spooler service is not reachable",
        'start it in a PowerShell opened with "Run as administrator": `Start-Service Spooler`',
    ),
)


def create_queue(device_id: str, tcp_port: int) -> Outcome:
    """Create or update the queue and its port for `127.0.0.1:tcp_port`. Raises QueueSetupError.

    The port's SNMP index is the TCP port, which the simulator's SNMP responder maps to the printer.
    """
    return _outcome(_run(_CREATE, Name=queue_name(device_id), Port=tcp_port, Driver=DRIVER))


def remove_queue(device_id: str) -> Outcome:
    """Delete the queue and its port; `changed` is False when neither existed. Raises QueueSetupError."""
    return _outcome(_run(_REMOVE, Name=queue_name(device_id)))


def run_powershell(script: str) -> Any:
    """Run `script` in Windows PowerShell and decode the JSON it prints. Raises QueueSetupError."""
    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-EncodedCommand",
        b64encode(script.encode("utf-16-le")).decode(),
    ]
    try:
        completed = subprocess.run(  # noqa: S603 - fixed program; the script is ours
            command, capture_output=True, timeout=POWERSHELL_TIMEOUT_SECONDS, check=False
        )
        return json.loads(completed.stdout.decode(errors="replace").strip().splitlines()[-1])
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
        raise QueueSetupError(
            "Windows PowerShell did not run the print queue commands",
            "check that `powershell.exe` starts in this terminal",
        ) from None


def _run(script: str, **values: str | int) -> Any:
    # Values are device ids (a-z, 0-9, -), port numbers and the driver name: quoted for PowerShell.
    assignments = "".join(
        f"${name} = {value}\n"
        if isinstance(value, int)
        else f"${name} = '{value.replace("'", "''")}'\n"
        for name, value in values.items()
    )
    return run_powershell(assignments + _PRELUDE + script)


def _outcome(result: Any) -> Outcome:
    notes: list[str] = list(map(str, result.get("notes") or ()))
    if result.get("ok"):
        return Outcome(bool(result.get("changed")), notes)
    error_id, step = str(result.get("error_id", "")), str(result.get("step", ""))
    if error_id == "spooler_stopped":
        raise QueueSetupError(
            "the Print Spooler service is not running",
            'start it in a PowerShell opened with "Run as administrator": `Start-Service Spooler`',
        )
    for hresult, message, fix in _KNOWN_FAILURES:
        if hresult in error_id.lower():
            raise QueueSetupError(f"{step} failed: {message}", fix)
    details = "; ".join([str(result.get("message", "")).strip(), *notes])
    raise QueueSetupError(
        f"{step} failed: {details}", "check the message above; `emupos doctor` checks the setup"
    )
