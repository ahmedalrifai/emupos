# windows-generic-text-arabic

Captured on Windows 11 Pro 26200 (September 2026) the same way as `windows-generic-text-receipt`: Notepad printing a UTF-8 text file to a "Generic / Text Only" queue. The file held two lines, `EMUPOS` and `المجموع 4.75`.

Commands in the input (count):

- CR (2)
- LF (7)
- text (2)
- unknown `0c` (1)

The driver replaced each of the seven Arabic characters with `.` (`2e`), so the printer receives `....... 4.75`. Arabic text cannot reach the printer through this driver; a POS has to send its own ESC/POS bytes (an Arabic code page or an image) as a raw job or to the printer's port.
