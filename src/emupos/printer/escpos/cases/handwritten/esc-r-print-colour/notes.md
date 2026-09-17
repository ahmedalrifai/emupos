# esc-r-print-colour

Hand-written. A kitchen ticket that prints its modifiers in red with `ESC r` (`esc_lr`): the
first with the ASCII parameters `'1'` and `'0'`, the second with the binary parameters `01` and
`00`. The printer is single-colour, so everything prints in black and no parameter prints as
text (issue #26).
Spec: receipt-printer, "Supported print commands".
