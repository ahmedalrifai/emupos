# Windows: serial devices

emupos cannot create serial ports on Windows. A serial device there (a scale, a serial scanner, a printer on a serial connection) opens a COM port that already exists, and your POS opens the other end of the link:

```yaml
  - id: deli
    type: scale
    profile: toledo8217-15kg
    connections:
      - serial: { port: COM5 }   # emupos opens COM5, the POS opens COM6
```

`serial: { pty: true }` is not available on Windows; the configuration is rejected with a pointer to this page.

## Getting a pair of COM ports

Windows has no built-in virtual serial port pairs. Pick one of these:

| Option | Works with Secure Boot on | Notes |
|---|---|---|
| Two USB serial adapters joined by a null-modem cable | yes | Real hardware, so the baud rate and parity on both sides must match, as with a real device. |
| com0com 3.0.0.0 | **no** | Free virtual port pairs. Blocked on current Windows 11 when Secure Boot is on (below). |
| com0com with Secure Boot turned off | yes, once it is off | Secure Boot is a firmware (UEFI) setting. Turning it off lowers the machine's protection against boot-level malware; decide that for your machine, not because emupos needs it. |
| Another virtual serial port driver | depends on the driver | Windows 10 1607 and later, with Secure Boot on, only load new kernel drivers signed through Microsoft (attestation or WHQL). Check that the driver you choose is. |

### com0com is blocked with Secure Boot on

The com0com 3.0.0.0 installer has a valid signature, but its kernel driver was signed with a 2016 certificate that Windows no longer accepts with Secure Boot on. It installs without a warning, then:

- Device Manager shows the com0com bus device with **Code 52** ("Windows cannot verify the digital signature for the drivers required for this device");
- no COM ports appear under "Ports (COM & LPT)";
- the Code Integrity event log has event 3004 for `com0com.sys`.

`emupos doctor` reports this as a com0com device with the problem `CM_PROB_UNSIGNED_DRIVER`. You can check it yourself in PowerShell:

```powershell
Get-PnpDevice -PresentOnly | Where-Object FriendlyName -like '*com0com*' | Format-List FriendlyName, Status, ConfigManagerErrorCode
Confirm-SecureBootUEFI
```

To remove it again, run `setupc remove 0` from the com0com folder (`C:\Program Files (x86)\com0com`) in a terminal opened with "Run as administrator".

### Creating a com0com pair (Secure Boot off)

In a terminal opened with "Run as administrator", in the com0com folder:

```powershell
.\setupc.exe install PortName=COM5 PortName=COM6
```

Give emupos one name and your POS the other. A virtual pair passes bytes whatever baud rate or parity each side sets, while a real device would misread them: see "Serial settings" below.

## Serial settings

emupos opens the port with the device profile's settings (a Toledo 8217 scale: 9600 baud, 7 data bits, even parity, 1 stop bit). On Windows emupos cannot see which settings the POS chose on its end, so there are no framing-mismatch warnings as on macOS. Set the POS to the profile's settings yourself.

## When the port does not open

| Message from `emupos run` | What to do |
|---|---|
| `no serial port named COM5` | The port does not exist. Check the name under "Ports (COM & LPT)" in Device Manager or with `[System.IO.Ports.SerialPort]::GetPortNames()`, create the pair, or connect the adapter. |
| `serial port COM5 is in use by another program` | emupos opens the port exclusively. Close the other program (often a terminal program or the POS pointed at the wrong end of the pair). |

`emupos doctor` checks every configured COM port and the com0com driver, and prints a fix for each problem.
