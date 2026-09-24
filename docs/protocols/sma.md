# SMA scale protocol

A simulated scale with the `sma-15kg` profile speaks the protocol the Scale Manufacturers Association publishes, which Brecknell, Avery Weigh-Tronix, Detecto and others implement. A POS sends one letter between two framing bytes, and the scale answers with the weight, its status and the unit it is reporting in.

The protocol is defined by **SMA SCP-0499, "Scale Serial Communication Protocol, Levels #1 and #2"**, First Edition approved 24 April 1999, Mod 1 dated 29 November 2005, published by the [Scale Manufacturers Association](https://www.scalemanufacturers.org/PDF/ScaleCommProtocol5199M1.pdf). This page describes what emupos sends in its own words; the standard itself is the SMA's document, and the section numbers in `src/emupos/scale/sma/sma.py` point into it.

The code is `src/emupos/scale/sma/sma.py`, and every reply on this page is asserted in `src/emupos/scale/sma/test_sma.py`.

Bytes on this page are written as characters where they are printable, and as `<LF>` (`0a`), `<CR>` (`0d`) and `<ESC>` (`1b`) otherwise. `>` is what the POS sends, `<` is what the scale answers.

## Connection

| Setting | Value |
|---|---|
| Connection | serial |
| Baud rate | 9600 |
| Data bits | 8 |
| Parity | none |
| Stop bits | 1 |

The serial port works exactly as it does for the [Toledo 8217 protocol](toledo8217.md#connection): on macOS and Linux emupos creates it and publishes a link, and a framing mismatch is reported the same way.

## Framing

Every command is `<LF>`, one command character, its data if it has any, and `<CR>`. Every reply begins with `<LF>` and ends with `<CR>`. Bytes that arrive outside those markers are not a command and are ignored, so a POS that sends a stray newline or a partial command cannot confuse the scale. A command split across several writes is answered once, when its `<CR>` arrives.

`<ESC>` is the exception. It is acted on wherever it appears, even in the middle of a half-sent command, and it is never answered.

## The standard reply

Most commands are answered with one message:

```
<LF> <s> <r> <n> <m> <f> <xxxxxx.xxx> <uuu> <CR>
```

| Field | Width | What emupos puts there |
|---|---|---|
| `<s>` | 1 | Scale status, below |
| `<r>` | 1 | Range, always `1`: every built-in profile is single-range |
| `<n>` | 1 | `G` gross, `N` net (a tare is set), `T` the tare itself; lower case in high resolution |
| `<m>` | 1 | `M` while the reading is in motion, a space when it is still |
| `<f>` | 1 | Reserved by the standard; always a space |
| weight | 10 | The weight in the current unit, right-justified, or ten `-` when an error is reported |
| `<uuu>` | 3 | The current unit: `kg_`, `lb_` and so on |

Scale status characters:

| `<s>` | Meaning | When emupos sends it |
|---|---|---|
| space | Nothing to report | The usual case |
| `Z` | Centre of zero | The gross weight is exactly 0 g |
| `O` | Over capacity | The gross weight is above the profile's capacity |
| `U` | Under capacity | The reported weight is below zero |
| `E` | Zero error | `Z` was refused because the reading is in motion |
| `T` | Tare error | `T` was refused because the reading is in motion |
| `I` | Initial-zero error | Never: emupos has no power-on zero cycle to fail |

With `E` and `T` the weight field is `----------`, as the standard requires, and the status overrides `Z`, `O` and `U`. A zero error lasts while the reading is in motion; a tare error is reported once and then cleared.

## Commands

The standard has two levels: Level #1 is what every compliant scale must answer, and Level #2 is everything else. emupos answers both.

| Command | Level | What it does |
|---|---|---|
| `W` | 1 | The weight now |
| `H` | 2 | The weight at ten times the resolution, with `<n>` in lower case |
| `P`, `Q` | 2 | The displayed weight, normal and high resolution. emupos displays what it reports, so these answer as `W` and `H` |
| `Z` | 1 | Zero the scale |
| `T` | 2 | Tare the weight on the platter |
| `T<weight>` | 2 | Set the tare to a weight you give, in the current unit |
| `M` | 2 | Report the tare weight, changing nothing |
| `C` | 2 | Clear the tare |
| `U` | 2 | Move to the next unit the profile lists, wrapping |
| `U<uuu>` | 2 | Report in that unit, if the profile lists it; an unlisted unit is ignored |
| `R`, `S` | 2 | Repeat the weight, normal and high resolution, until the next command |
| `D` | 1 | Diagnostics. emupos has no hardware to fail, so all four indicators are spaces |
| `A`, `B` | 1 | The About dialogue, below |
| `I`, `N` | 2 | The Information dialogue, below |
| `X c` | 2 | The manufacturer's own extension. emupos defines none, so it answers `?` |
| `<ESC>` | 1 | Abort: stop a repeat, forget a half-sent command, answer nothing |

Anything else is answered `<LF>?<CR>`.

The standard also defines `<LF>!<CR>` for a communication error such as a parity error. emupos never sends it: it cannot see a framing error at this level, and reports one as a `connection.framing-mismatch` event instead.

### Examples

With `sma-15kg` reporting kilograms and 1.250 kg on the platter:

```
> <LF>W<CR>
< <LF> 1G       1.250kg_<CR>

> <LF>H<CR>
< <LF> 1g      1.2500kg_<CR>

> <LF>U<CR>
< <LF> 1G        2.76lb_<CR>
```

Taring a 200 g container, then weighing 1.450 kg on top of it:

```
> <LF>T<CR>
< <LF> 1N       0.000kg_<CR>
> <LF>W<CR>
< <LF> 1N       1.250kg_<CR>
> <LF>M<CR>
< <LF> 1T       0.200kg_<CR>
```

Zeroing while the reading is still in motion:

```
> <LF>Z<CR>
< <LF>E1GM ----------kg_<CR>
```

## Continuous weight

`R` and `S` answer at once and then keep repeating the weight to the connection that asked, every `repeat_interval_ms` from the profile, 200 ms by default. The standard says only "continuously", so each model picks its own rate and this is the knob to match yours.

Any further command from that connection stops the repeats, including one the scale does not recognise, and including `<ESC>`. Other connections are unaffected: a repeat goes only to the host that asked for it.

## About and Information

`A` starts the About dialogue and each `B` returns the next field. `I` starts the Information dialogue and each `N` returns the next field. Both end with `END:`, and one command past the end is answered `?`. Each dialogue has its own place in each connection, so two POS applications can read them at the same time without stepping on each other.

About, then Information:

```
> <LF>A<CR>                > <LF>I<CR>
< <LF>SMA:2/1.0<CR>        < <LF>SMA:2/1.0<CR>
> <LF>B<CR>                > <LF>N<CR>
< <LF>MFG:emupos<CR>       < <LF>TYP:S<CR>
> <LF>B<CR>                > <LF>N<CR>
< <LF>MOD:SMA 15kg<CR>     < <LF>CAP:kg_:15.000:5:3<CR>
> <LF>B<CR>                > <LF>N<CR>
< <LF>REV:1.0<CR>          < <LF>CMD:HPQRSTMCU<CR>
> <LF>B<CR>                > <LF>N<CR>
< <LF>END:<CR>             < <LF>END:<CR>
```

The maker is `emupos` rather than a vendor's name, because this is a simulated scale and not an imitation of any particular model. `CAP` reports the capacity, count-by and decimal places of the unit in use, so it changes when you switch units. `CMD` lists the Level #2 commands emupos answers.

## Units

The profile lists the units the scale offers, in the order its unit key cycles them. The first is the unit after start. Each entry gives the unit's three-character name, how many decimal places it shows and what it counts by in the last of them:

```yaml
units:
  - { unit: kg_, decimals: 3, count_by: 5 } # 0.005 kg
  - { unit: lb_, decimals: 2, count_by: 1 } # 0.01 lb
```

The weight is held in whole grams and converted when it is reported, using the exact definition of each unit, so a pound is 453.59237 g. The value is rounded to the unit's count-by, halves away from zero.

emupos knows `kg_`, `g__`, `mg_`, `lb_`, `oz_`, `ozt`, `ct_`, `gn_`, `dwt`, `t__` and `ton`. The composite `l/o` (pounds and ounces together) is not among them.

The unit belongs to the scale, not to a connection: a real scale has one unit key, and every connected host sees the same reading. It is also in the control API, as `state.unit`, so a test can read it without speaking the protocol.

## What is not simulated

- Multi-range scales and weight classifiers (`TYP:C`). Every built-in profile is a single-range scale.
- The `l/o` unit, and the jewellery and parts-per-pound units the standard lists but which no built-in profile uses.
- The communication-error reply, as described above.
- The NCI protocol, which vendors list separately from SMA. It is a different command set and needs its own document.
