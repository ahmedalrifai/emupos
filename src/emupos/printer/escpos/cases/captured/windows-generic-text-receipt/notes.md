# windows-generic-text-receipt

Captured on Windows 11 Pro 26200 (September 2026) with `spikes/windows-snmp/snmp_spike.py` as the print sink, behind a Standard TCP/IP port queue using the built-in "Generic / Text Only" driver (spike 1.3). A six-line UTF-8 text file was printed from Notepad with Ctrl+P. These are the bytes a POS gets when it prints ordinary text through such a queue instead of sending raw ESC/POS.

Commands in the input (count):

- CR (6)
- LF (11)
- text (6)
- unknown `0c` (1)

The driver sends no ESC/POS at all: a top margin of line feeds, a left margin of 7 spaces, CR LF line ends and a form feed (`0c`) at the end, which emupos reports as an unknown command. The empty line between the address and the items in the text file was not sent. The last line has no line feed; emupos prints it when the job ends.
