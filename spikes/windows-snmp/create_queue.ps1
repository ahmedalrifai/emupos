<#
.SYNOPSIS
  SNMP spike (task 1.3): create a Standard TCP/IP port and a "Generic / Text Only" queue
  that print to 127.0.0.1, with SNMP status enabled.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\create_queue.ps1
  powershell -ExecutionPolicy Bypass -File .\create_queue.ps1 -Name emupos-spike2 -PortNumber 9101 -DeviceIndex 2 -Community back
#>
param(
    [string] $Name = "emupos-spike",
    [int] $PortNumber = 9100,
    [string] $Community = "public",
    [int] $DeviceIndex = 1,
    [string] $Driver = "Generic / Text Only",
    [switch] $SkipAdminCheck  # Microsoft's docs say Add-PrinterPort needs no admin; try it and record
)
$ErrorActionPreference = "Stop"

$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin -and -not $SkipAdminCheck) {
    Write-Host "Run this from PowerShell opened with 'Run as administrator' (or pass -SkipAdminCheck to see what fails)." -ForegroundColor Red
    exit 1
}

if (Get-Printer -Name $Name -ErrorAction SilentlyContinue) {
    Write-Host "Queue '$Name' already exists. Run .\remove_queue.ps1 -Name $Name first." -ForegroundColor Red
    exit 1
}

if (-not (Get-PrinterDriver -Name $Driver -ErrorAction SilentlyContinue)) {
    Write-Host "Installing the inbox driver '$Driver'..."
    Add-PrinterDriver -Name $Driver
}

Write-Host "Creating port '$Name' -> 127.0.0.1:$PortNumber (SNMP index $DeviceIndex, community '$Community')"
Add-PrinterPort -Name $Name -PrinterHostAddress "127.0.0.1" -PortNumber $PortNumber -SNMP $DeviceIndex -SNMPCommunity $Community

try {
    Write-Host "Creating queue '$Name' with driver '$Driver'"
    Add-Printer -Name $Name -DriverName $Driver -PortName $Name
} catch {
    Write-Warning "Queue creation failed; removing the port again. $_"
    Remove-PrinterPort -Name $Name
    exit 1
}

Get-PrinterPort -Name $Name | Format-List Name, PrinterHostAddress, PortNumber, SNMPEnabled, SNMPCommunity, SNMPIndex
Get-Printer -Name $Name | Format-List Name, DriverName, PortName, PrinterStatus
