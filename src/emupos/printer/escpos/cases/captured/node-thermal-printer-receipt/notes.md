# node-thermal-printer-receipt

Captured on macOS (September 2026) with `spikes/printer-capture/capture.py` from node-thermal-printer 4.6.1 (ISC), type EPSON.
Job `receipt` in `spikes/printer-capture/node_jobs.mjs`.

Commands in the input (count):

- ESC ! (3)
- ESC - (2)
- ESC @ (1)
- ESC E (2)
- ESC a (2)
- ESC d (2)
- ESC p m=0 (1)
- ESC t (1)
- GS ! (1)
- GS ( k cn=49 fn=65 (1)
- GS ( k cn=49 fn=67 (1)
- GS ( k cn=49 fn=69 (1)
- GS ( k cn=49 fn=80 (1)
- GS ( k cn=49 fn=81 (1)
- GS H (2)
- GS V m=0 (1)
- GS f (2)
- GS h (2)
- GS k m=67 (1)
- GS k m=73 (1)
- GS w (2)
- LF (7)
- text (7)
- unknown 01 (1)

Observed: `openCashDrawer()` sends `1b 70 00 1b 70 01` (ESC p without t1 t2). A printer reads
`1b 70` as t1 t2 of the first kick (ON time 54 ms) and skips the stray `01`, which is what
emupos does too.
