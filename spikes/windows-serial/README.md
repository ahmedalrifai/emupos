# Windows serial spike (task 1.1)

**Question.** Does the signed com0com 3.0.0.0 driver load on Windows 10/11 with Secure Boot on, or is it blocked (Device Manager "Code 52")? And against a com0com pair, is serialx (asyncio) reliable, or should emupos default to pyserial in a worker thread?

Record everything in `docs/spikes/windows-serial.md`. Time needed: about 45 minutes. You install a kernel driver; step 8 removes it.

## 1. Record the machine

Open **PowerShell as administrator** (Start, type `PowerShell`, right-click, *Run as administrator*):

```powershell
Confirm-SecureBootUEFI
Get-ComputerInfo | Select-Object OsName, OsVersion, OsBuildNumber
```

- `True` = Secure Boot on, `False` = off. "Cmdlet not supported on this platform" = legacy BIOS (no Secure Boot).
- Note whether this is a physical PC or a VM.

## 2. Download the signed com0com

Download **`com0com-3.0.0.0-i386-and-x64-signed.zip`** from the official project page:

https://sourceforge.net/projects/com0com/files/com0com/3.0.0.0/

> **Do not use com0com.com** or any other download site. It is not the project's site. The project lives on SourceForge (com0com.sourceforge.net).

Check the file before running anything:

```powershell
Get-FileHash .\com0com-3.0.0.0-i386-and-x64-signed.zip -Algorithm SHA256
```

The copy downloaded from SourceForge on 2026-09-13 had SHA-256 `6e5d4359865277430d4ae88c73fb7e648a0ed8e81aea5002478179cfcb0bb0e1`. If yours differs, stop and report it.

Unzip it and record the installer's signature (it matters for Windows' driver signing rules):

```powershell
Get-AuthenticodeSignature .\Setup_com0com_v3.0.0.0_W7_x64_signed.exe |
  Format-List Status, StatusMessage, @{n='Signer';e={$_.SignerCertificate.Subject}}, @{n='NotBefore';e={$_.SignerCertificate.NotBefore}}, @{n='NotAfter';e={$_.SignerCertificate.NotAfter}}
```

## 3. Install

1. Right-click `Setup_com0com_v3.0.0.0_W7_x64_signed.exe` (use the `x86` one only on 32-bit Windows), *Run as administrator*.
2. On the components page, **untick the port pair options** ("CNCA0 <-> CNCB0" and "COM# <-> COM#") if they are shown; step 4 creates the pair by command so every run is the same.
3. If Windows asks "Would you like to install this device software?", choose *Install*.
4. Write down every prompt or warning you saw.

## 4. Create a port pair

Open the Start menu shortcut **com0com > Setup Command Prompt** (right-click, *Run as administrator*). If there is no shortcut, open an admin Command Prompt and `cd` to the install folder; look in both `C:\Program Files (x86)\com0com` and `C:\Program Files\com0com`.

```bat
setupc install PortName=COM# PortName=COM#
setupc list
```

`PortName=COM#` asks Windows' "Ports" class installer to assign real COM numbers, so the ports appear under **Ports (COM & LPT)**, where POS software looks. `setupc list` prints something like:

```
       CNCA0 PortName=COM#,RealPortName=COM3
       CNCB0 PortName=COM#,RealPortName=COM4
```

Rename them to COM5/COM6 if those numbers are free (otherwise use the numbers you got in every command below):

```bat
setupc change CNCA0 RealPortName=COM5
setupc change CNCB0 RealPortName=COM6
setupc list
```

In this kit **COM5 (CNCA0) is the "sim" end** (emupos) and **COM6 (CNCB0) is the "client" end** (the POS).

Note: `setupc install PortName=COM5 PortName=COM6` also creates a pair, but those ports sit in the "com0com - serial port emulators" class instead of Ports, and some software won't list them. If you try it, record it separately.

## 5. Check whether the driver loaded (Code 52)

In **Device Manager** (`devmgmt.msc`) expand *Ports (COM & LPT)* and *com0com - serial port emulators*. A yellow triangle means a problem: open *Properties*; **Code 52** reads "Windows cannot verify the digital signature for the drivers required for this device".

Or in PowerShell:

```powershell
Get-PnpDevice -PresentOnly | Where-Object { $_.FriendlyName -like '*com0com*' } |
  Format-List FriendlyName, Class, Status, ConfigManagerErrorCode, Problem
[System.IO.Ports.SerialPort]::GetPortNames()
```

- `Status OK` and `ConfigManagerErrorCode 0`: loaded. `Status Error` with `52`: blocked by driver signature enforcement.
- *Properties > Driver > Driver Details* shows the running `com0com.sys` version.

If you get Code 52: take a screenshot, fill in the template, skip to step 8. (Turning Secure Boot off to compare is optional and only safe if you have your BitLocker recovery key; otherwise don't.)

## 6. Run the spike

Close anything that might hold COM5/COM6 (PuTTY, Arduino IDE, POS software). From the repository root, in a normal PowerShell:

```powershell
uv run spikes/windows-serial/serial_spike.py COM5 COM6 --label default
```

It runs 100 cycles per backend (serialx, then pyserial), printing progress every 10 cycles, then writes `spikes/windows-serial/result-serialx-default.json` and `result-pyserial-default.json`. Each cycle: open both ends, send all 256 byte values each way, close the client, write from the sim with the client closed, reopen the client and look for stale bytes, round trip again. At the end it checks a client at 9600 7E1.

Expect 2 to 20 minutes. Every step has a timeout, so it should never hang. If nothing is printed for 2 minutes, press Ctrl+C and write down the last line.

Then repeat with com0com set to behave like a real null-modem cable (its ReadMe: "EmuOverrun" drops data nobody reads, "EmuBR" paces data at the baud rate). In the Setup Command Prompt:

```bat
setupc change CNCA0 EmuOverrun=yes,EmuBR=yes
setupc change CNCB0 EmuOverrun=yes,EmuBR=yes
setupc list
```

```powershell
uv run spikes/windows-serial/serial_spike.py COM5 COM6 --label emu
```

Useful options: `--backend serialx` or `--backend pyserial` to run one backend, `--cycles 20` for a quick check.

## 7. GitHub-hosted runners (optional)

Task 1.1 also asks whether com0com installs on a GitHub-hosted Windows runner. Not covered by this kit; the com0com ReadMe documents a silent install (`setup.exe /S`, with the environment variable `CNC_INSTALL_COMX_COMX_PORTS=YES` to create a COM# pair). Record "untested" if you don't try it.

## 8. Uninstall

In the Setup Command Prompt (admin):

```bat
setupc list
setupc remove 0
```

(`0` is the number in `CNCA0`/`CNCB0`.) Then uninstall **Null-modem emulator (com0com)** from *Settings > Apps > Installed apps* (or the com0com *Uninstall* shortcut). In Device Manager, *View > Show hidden devices* should show no com0com devices left.

## Send back

`docs/spikes/windows-serial.md` filled in, the `result-*.json` files, the `setupc list` output and any screenshots.
