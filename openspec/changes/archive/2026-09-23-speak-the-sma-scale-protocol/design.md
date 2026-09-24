## Context

The source is [SMA SCP-0499][sma], *Scale Serial Communication Protocol, Levels #1 and #2*, First
Edition approved 24 April 1999, Mod 1 dated 29 November 2005, published by the Scale Manufacturers
Association. The SMA's own server refuses automated requests, so the copy read while writing this
change was the Internet Archive's [snapshot of 16 January 2021][archive]. The document is
copyrighted, so `docs/protocols/sma.md` describes the wire format in its own words and cites it,
the way `docs/protocols/toledo8217.md` does.

Every exchange is framed. A command is `<LF> c <CR>`, and the standard reply is

```
<LF> <s> <r> <n> <m> <f> <xxxxxx.xxx> <uuu> <CR>
      │   │   │   │   │    │           └── unit, 3 characters: lb_, kg_, l/o, g__, …
      │   │   │   │   │    └── weight, fixed at 10 characters
      │   │   │   │   └── reserved for future use
      │   │   │   └── M in motion, space still
      │   │   └── G gross, N net, T tare, g/n the same in high resolution
      │   └── range, always 1 here
      └── Z centre of zero, O over capacity, U under capacity, E/I/T errors, space none
```

Level #1 is `W Z D A B <ESC>`, which every compliant scale must answer. Level #2 adds
`H P Q R S T M C U I N X`, and a scale is Level #2 compliant if it answers even one of them. This
change implements both levels in full, so the profile can honestly report `SMA:2/1.0`.

What exists in emupos: `Scale` holds grams, tare and settling and answers through one protocol
object per connection, created from `PROTOCOLS[profile.protocol]`. `Toledo8217.receive(data, state)`
is pure — bytes and a state snapshot in, bytes out. Zero and tare exist only as API and CLI
operations, and refusing them while the reading is in motion raises `ScaleInMotionError`.

[sma]: https://www.scalemanufacturers.org/PDF/ScaleCommProtocol5199M1.pdf
[archive]: https://web.archive.org/web/20210116185103/https://scalemanufacturers.org/PDF/ScaleCommProtocol5199M1.pdf

## Goals / Non-Goals

**Goals:**

- A POS driver written for an SMA scale talks to emupos and sees a scale that behaves like one.
- The second protocol establishes the shape every later protocol uses (CAS, NCI, Dialog 06).
- Toledo behaviour is unchanged, byte for byte.

**Non-Goals:**

- NCI, which is a different protocol with no citable document yet.
- Multi-range scales, weight classifiers (`TYP:C`) and the parts-per-pound and jewellery units.
- Reporting a communication error (`!`): the simulator has no parity or framing errors to detect
  at this layer.

## Decisions

### D1. A protocol may act on the scale, through an interface the scale implements

`Z`, `T`, `C` and `U` change the device. Rather than pass the `Scale` itself into the protocol, the
scale passes a small operations interface: `state()`, `zero()`, `tare(grams=None)`, `clear_tare()`
and `select_unit(unit)`. `zero()` and `tare()` return whether the scale accepted the operation, so
a refusal is a value, not an exception — over SMA a refusal is a status indicator, while the API
still answers 409.

This keeps the rule the codebase already has: the scale is the only thing that changes scale state
and publishes `scale.weight.changed`. It also keeps ordering honest — `Z` zeroes first and then
formats the reply from the state that results, which a "return the actions you want" design cannot
do without two passes.

Alternatives: returning actions for the scale to apply (needs a second pass to format the reply);
handing the protocol the `Scale` (any protocol could then reach past the interface).

### D2. The unit lives on the scale; the profile lists which units a model has

`units` in the profile is an ordered list, each entry naming the unit, its decimal places and its
count-by. The first entry is the unit after start, `U` moves to the next and wraps, and `U<uuu>`
selects a listed unit. An unlisted unit is ignored, which is what the standard says a scale does.

The unit is device state, not connection state, because a real scale has one unit key and every
connected host sees the same reading. `GET /api/v1/devices/{id}` therefore reports it.

The weight itself stays in whole grams. Grams are the truth; a unit is a way of reporting it.

### D3. Rounding happens in the display unit, with the profile's count-by

`division_grams` stays the scale's resolution, shared by every protocol. On top of it, SMA rounds
the converted value to the unit's count-by — a 15 kg x 5 g scale reporting pounds counts by 0.01 lb,
not by an odd fraction of a gram. Conversion uses exact factors as `Decimal` (1 lb = 453.59237 g,
1 oz = 28.349523125 g), and the same rule Toledo already uses: round half away from zero.

### D4. Error indicators come from what the scale already refuses

- `Z` while the reading is in motion → `E`, zero error, which the standard says clears when the
  condition clears. It does: the next command after settling reports no error.
- `T` while in motion → `T`, tare error, which the standard says clears after being read. It is a
  one-shot flag on the connection that asked.
- `O`, `U` and `Z` (centre of zero) come from the weight, as they do for Toledo.
- `I`, initial-zero error, is never reported: emupos has no power-on zero cycle to fail.

In every error case the weight field is centre dashes rather than a number, as the standard
requires.

### D5. `R` and `S` are per connection, paced by the profile

Continuous weight belongs to the connection that asked. The standard says "continuously" without a
rate, so `repeat_interval_ms` is a profile field with a default a real scale plausibly uses; it is
the knob to turn when a POS's timing assumptions matter. `Scale.next_deadline()` already exists for
settling and grows to cover the next repeat, and `tick` writes the repeats that are due. Any
command from that connection stops the repeat, including a command the scale does not recognise.

### D6. About and Information are a pointer per connection

`A` answers `SMA:2/1.0` and resets that connection's `B` pointer; each `B` returns the next field —
maker, model, revision, serial number, then `END:`; a `B` past the end answers `?`. `I` and `N`
work the same way over the scale's type, capacity line and supported commands. The maker, model,
revision and serial number are profile fields, reusing the printable-ASCII text type added for the
printer's `GS I` values. The `CAP` line and the `CMD` list are derived, so they cannot drift from
what the scale actually does.

### D7. `ESC` is handled before framing

`ESC` (`1b`) is the one command outside `<LF>…<CR>`, and it must work whatever the scale is doing.
The protocol checks for it byte by byte, before the frame parser: it clears a partly received
frame, stops a repeat, resets the About and Information pointers, and answers nothing. The scale
itself is not reset — the weight on the platter does not change because a host gave up.

### D8. Per-protocol profile settings, discriminated by `protocol`

`reply_integer_digits` and `reply_decimals` describe a Toledo reply and mean nothing to SMA, while
`units`, the About fields and `repeat_interval_ms` mean nothing to Toledo. The profile becomes a
discriminated union on `protocol`, like the device union on `type`: shared fields (capacity,
division, settle time, serial framing) on the base, protocol fields on each member. A profile that
names one protocol and carries the other's settings then fails validation with a path that names
the key, instead of being silently ignored.

**The Toledo member keeps its keys exactly where they are.** `reply_integer_digits` and
`reply_decimals` stay at the root of a `toledo8217` profile, so every profile written against
today's shape — built-in or user-provided — loads unchanged and no one has to edit a file. Nesting
them under a protocol block would read a little tidier and would break every existing profile to
buy it, which is not a trade worth making in a 0.x beta that people are already running.

## Risks / Trade-offs

- **A profile that carried a meaningless key now fails.** A Toledo profile that happened to define
  something the protocol never read is now an error rather than silence. That is the point of the
  union, it names the key, and a profile written from the documented shape is unaffected.
- **The whole command set is a lot of surface for one change.** The tasks are grouped so the
  protocol can land in working stages — framing and weighing first, then zero and tare, then units,
  then the dialogues and continuous weight — each with its own tests.
- **A repeat interval that is wrong for a given model** → it is a profile field, not a constant, so
  a profile for a faster or slower scale sets its own.
- **Double rounding between `division_grams` and a unit's count-by** → the reported value is
  computed from the exact grams once, not rounded twice; `division_grams` describes what the scale
  can read, the count-by what it displays.
