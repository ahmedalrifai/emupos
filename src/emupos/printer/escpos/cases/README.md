# ESC/POS rendering cases

Each folder holds one print job and what emupos renders for it with the `epson-tm-t20iii`
profile:

- `input.hex`: the bytes the POS sends, as spaced hex;
- `expected.png` and `expected.txt`: the receipt image and text dump (a job that prints nothing,
  such as a drawer kick, has an empty `expected.txt` and no image);
- `notes.md`: where the bytes come from and what they exercise.

`captured/` holds real traffic recorded with `spikes/printer-capture/`; `handwritten/` holds
jobs written for one requirement. `src/emupos/printer/escpos/test_cases.py` checks them all.

To add a case, create the folder with `input.hex` and `notes.md` and run the tests: missing
expected files are generated. Look at the new `expected.png` before committing it.

After an intended rendering change, regenerate every case and review the image diffs:

```sh
EMUPOS_UPDATE_CASES=1 uv run pytest src/emupos/printer/escpos/test_cases.py
```
