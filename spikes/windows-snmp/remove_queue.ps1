<#
.SYNOPSIS
  SNMP spike (task 1.3): remove the queue and port made by create_queue.ps1.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\remove_queue.ps1
  powershell -ExecutionPolicy Bypass -File .\remove_queue.ps1 -Name emupos-spike2
#>
param(
    [string] $Name = "emupos-spike",
    [switch] $SkipAdminCheck
)
$ErrorActionPreference = "Stop"

$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin -and -not $SkipAdminCheck) {
    Write-Host "Run this from PowerShell opened with 'Run as administrator' (or pass -SkipAdminCheck to see what fails)." -ForegroundColor Red
    exit 1
}

$removed = $false
if (Get-Printer -Name $Name -ErrorAction SilentlyContinue) {
    Remove-Printer -Name $Name
    Write-Host "Removed queue '$Name'"
    $removed = $true
}
if (Get-PrinterPort -Name $Name -ErrorAction SilentlyContinue) {
    # The spooler can hold the port for a moment after the queue is deleted.
    for ($attempt = 1; $attempt -le 5; $attempt++) {
        try {
            Remove-PrinterPort -Name $Name
            Write-Host "Removed port '$Name'"
            $removed = $true
            break
        } catch {
            if ($attempt -eq 5) { throw }
            Start-Sleep -Seconds 1
        }
    }
}
if (-not $removed) {
    Write-Host "Nothing to remove: no queue or port named '$Name'."
}
