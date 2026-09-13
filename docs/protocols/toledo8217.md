# Toledo 8217 scale protocol

A simulated scale with the `toledo8217-15kg` profile speaks the Mettler Toledo 8217 protocol on a serial port. Many POS systems read counter scales this way: the POS sends one letter, the scale answers with the weight or with a status byte.

emupos implements the wire contract that common POS clients rely on, such as Odoo's public Toledo 8217 scale driver: 9600 baud, 7 data bits, even parity, the `W` weight request and the `E`…`F` echo probe. Anything else is answered as a bad command.

The code is `src/emupos/scale/toledo8217/toledo8217.py`. Every dialogue on this page is also a test fixture in `src/emupos/scale/toledo8217/dialogues/`.

All bytes on this page are hexadecimal. `>` is what the POS sends, `<` is what the scale answers.

## Connection

| Setting | Value |
|---|---|
| Connection | serial |
| Baud rate | 9600 |
| Data bits | 7 |
| Parity | even |
| Stop bits | 1 |

On macOS and Linux emupos creates the serial port itself (`serial: { pty: true }`) and publishes it as a link: `$TMPDIR/emupos/<device id>`, or `/tmp/emupos/<device id>` when `TMPDIR` is not set. `emupos run` and `emupos devices` print the exact path. Open that path in your POS; it is not listed by port enumeration, so type the path in.

If the POS opens the port with other settings, emupos still answers but shows a warning and publishes a `connection.framing-mismatch` event. macOS lets emupos see the baud rate, data bits and parity; Linux shows only the baud rate. For example, opening the port as 8N1 on macOS gives:

```
warning: deli: serial framing mismatch on $TMPDIR/emupos/deli: data_bits expected 7 observed 8, parity expected even observed none
```

## Commands

The scale reads one byte at a time. A write may contain several commands; each gets its own reply.

| Byte | Name | Reply |
|---|---|---|
| `57` (`W`) | Weight request | A [weight reply](#weight-reply) or a [status reply](#status-reply) |
| `45` (`E`) | Echo probe | `02 45 0d`, then every following byte is echoed back until `F` |
| `46` (`F`) | End of the echo probe | Nothing (only while echoing; otherwise it is an unrecognised command) |
| `0d`, `0a` (CR, LF) | Line terminators | Nothing: ignored between commands |
| anything else | Unrecognised command | A status reply with the bad command bit set |

Replies always start with STX (`02`) and end with CR (`0d`).

## Weight reply

When the weight can be reported, the reply to `W` is:

```
02  <weight in kilograms, ASCII>  [4e]  0d
STX  e.g. "01.250"                 N    CR
```

| Part | Meaning |
|---|---|
| `02` | STX |
| weight | Kilograms with a decimal point. The profile sets the format: `reply_integer_digits: 2` and `reply_decimals: 3` give `01.250`. |
| `4e` (`N`) | Present only while a tare is set: the weight is the net weight. |
| `0d` | CR |

The reported weight is the **net** weight (gross minus tare) while a tare is set, and the **gross** weight otherwise.

The weight can be reported when all of these are true:

- the reading is stable;
- the gross weight is not above the profile's capacity (15000 g for `toledo8217-15kg`; exactly 15000 g is fine);
- the reported weight is not below 0 g.

Otherwise the scale sends a status reply.

### Rounding to the scale division

The profile's `division_grams` is the scale's resolution (5 g for `toledo8217-15kg`). The weight in a reply is rounded to the nearest division, with halves rounded away from zero:

| Weight on the scale | Reply | Text |
|---|---|---|
| 1250 g | `02 30 31 2e 32 35 30 0d` | `01.250` |
| 1252 g | `02 30 31 2e 32 35 30 0d` | `01.250` |
| 1253 g | `02 30 31 2e 32 35 35 0d` | `01.255` |
| 15000 g | `02 31 35 2e 30 30 30 0d` | `15.000` |
| 0 g | `02 30 30 2e 30 30 30 0d` | `00.000` |

Motion, capacity and zero are always judged on the exact grams, never on the rounded value: 15001 g is over a 15000 g capacity.

## Status reply

When the weight cannot be reported, and in reply to an unrecognised command, the scale sends:

```
02 3f <status> 0d
STX ?  status  CR
```

The status byte has every bit that applies:

| Bit | Value | Meaning | Set when |
|---|---|---|---|
| 0 | `01` | In motion | the reading is not stable yet |
| 1 | `02` | Over capacity | the gross weight is above the profile's capacity |
| 2 | `04` | Under zero | the reported weight is below 0 g |
| 3 | `08` | — | never |
| 4 | `10` | Center of zero | the gross weight is exactly 0 g |
| 5 | `20` | Net weight | a tare is set |
| 6 | `40` | Bad command | only in the reply to an unrecognised command |
| 7 | `80` | — | never |

Bits 3 and 7 are never set, so the status byte is always 7-bit and never equals CR (`0d`) or LF (`0a`).

"Center of zero" and "net weight" do not stop a weight reply on their own: at 0 g, `W` still gets `00.000`. You see those bits only in a status reply, for example `02 3f 50 0d` when an unknown byte arrives while the scale is empty.

## Echo probe

POS clients check that a Toledo scale is connected by sending `E` followed by some bytes. The scale answers `02 45 0d` and then echoes every byte back unchanged until it receives `F`. `F` ends the probe and gets no reply. After that, requests are answered normally.

```
> 45 68 65 6c 6c 6f        E h e l l o
< 02 45 0d 68 65 6c 6c 6f
> 46                       F: no reply
> 57
< 02 30 31 2e 32 35 30 0d  01.250
```

## Putting weight on the scale

A POS never changes the weight: a person does, by putting something on the scale. With emupos, that person uses the CLI (or an automated test uses the control API):

| On a real scale you… | With emupos |
|---|---|
| put 1.25 kg of tomatoes on it | `emupos scale set 1.25kg` (or `1250g`) |
| put it down so it is still wobbling | `emupos scale set 1.25kg --unstable` |
| press ZERO | `emupos scale zero` |
| press TARE with an empty container on it | `emupos scale tare` |
| overload it | `emupos scale set 16kg` |
| zero it with a container on, then take the container off | `emupos scale set -- -100g` |

The matching API calls are `PUT /api/v1/devices/{id}/weight` with `{"grams": 1250, "stable": true}`, `POST /api/v1/devices/{id}/zero` and `POST /api/v1/devices/{id}/tare`. See [automation.md](../automation.md).

- **Settling.** An unstable weight is reported as in motion until the profile's `settle_ms` has passed (500 ms for `toledo8217-15kg`), then it becomes stable at the same weight. Setting the weight again restarts the wait.
- **Zero** sets the gross weight to 0 g and clears the tare.
- **Tare** makes the current gross weight the tare. On an empty scale (0 g or less) it clears the tare.
- Zero and tare are refused while the reading is in motion, as on a real scale: the CLI exits with status 1 and the API answers 409 with code `scale_in_motion`.
- Weights are whole grams.

Every reply the scale sends publishes a `scale.request.answered` event with the request and reply bytes; `emupos run` shows them live:

```
00:07:47.768  deli   scale.request.answered        57 → 02 30 31 2e 32 35 30 0d
```

Bytes echoed during a probe do not publish events.

## Example dialogues

Each block starts from the scale state given in its title.

**Stable 1250 g, no tare**

```
> 57
< 02 30 31 2e 32 35 30 0d          01.250
```

**Tare 200 g, gross 1450 g**

```
> 57
< 02 30 31 2e 32 35 30 4e 0d       01.250N (net)
```

**Unstable 1250 g, settle time 500 ms**

```
                                   emupos scale set 1.25kg --unstable
> 57                               100 ms later
< 02 3f 01 0d                      in motion
> 57                               600 ms after the set
< 02 30 31 2e 32 35 30 0d          01.250
```

**Over capacity: 15001 g on a 15000 g scale**

```
> 57
< 02 3f 02 0d
```

**Under zero: -100 g, no tare**

```
> 57
< 02 3f 04 0d
```

**Net weight below zero: tare 200 g, gross 100 g**

```
> 57
< 02 3f 24 0d                      under zero + net
```

**Several conditions: tare 200 g, unstable 16000 g**

```
> 57
< 02 3f 23 0d                      in motion + over capacity + net
```

**Unrecognised command, stable 1250 g**

```
> 58                               X
< 02 3f 40 0d                      bad command
> 57
< 02 30 31 2e 32 35 30 0d          the state is unchanged
```

**Line terminators after a request**

```
> 57 0d 0a
< 02 30 31 2e 32 35 30 0d          one reply only
```

## Try it by hand

With `emupos run --demo` running on macOS or Linux, set a weight and read it with [pyserial](https://pyserial.readthedocs.io/), the way a POS would:

```sh
emupos scale set 1.25kg
uv run --no-project --with pyserial python -c "import serial; s = serial.Serial('${TMPDIR:-/tmp}/emupos/deli', 9600, bytesize=7, parity='E', timeout=1); s.write(b'W'); print(s.read_until(b'\r'))"
```

```
b'\x0201.250\r'
```

## Limitations

- Only `W`, `E` and `F` are commands. Any other byte gets the bad command reply; the scale cannot be zeroed or tared over the wire.
- The serial port is created by emupos on macOS and Linux only. Opening an existing serial port (`serial: { port: ... }`, such as one end of a com0com pair on Windows) is not available yet, so the scale cannot run on Windows today.
- emupos's tests use the dialogues on this page. They do not run any POS client's driver against the simulator.
