## Why

A scale speaks one protocol today, Mettler Toledo 8217, and a POS written for a North American
scale speaks another (issue #21). The Scale Manufacturers Association publishes the one that
several vendors implement, SMA SCP-0499, so a POS driver written against a Brecknell, Avery or
Detecto scale has nothing to talk to in emupos.

The scale device already models what the protocol reports: gross weight, tare, motion, capacity and
settling. What is missing is a second protocol over that state — and the seam that lets a protocol
do more than read it, because SMA commands zero and tare the scale, which Toledo never does.

## What Changes

- **A second scale protocol, `sma`**, chosen per profile the way `toledo8217` already is, with a
  built-in profile for a North American counter scale.
- **The whole published command set**, because half a protocol fails in ways that are hard to tell
  from a bug: weighing (`W`, `H`, `P`, `Q`), zero and tare (`Z`, `T`, `T<weight>`, `M`, `C`),
  units (`U`, `U<uuu>`), continuous weight (`R`, `S`), diagnostics (`D`), the About and Information
  dialogues (`A`/`B`, `I`/`N`), the manufacturer extension (`X c`) and the abort character (`ESC`).
- **Protocols can change the scale, not only read it.** `Z`, `T`, `C` and `U` act on the device. A
  protocol returns the actions it wants applied and the scale applies them, so the scale stays the
  only thing that mutates state and keeps publishing `scale.weight.changed` as it does today.
- **A scale reports weight in a unit.** The profile lists the units a model offers, in the order its
  unit key cycles them, each with its count-by and decimal places. The first is the unit after
  start. `U` cycles, `U<uuu>` selects, and an unknown unit is ignored, as the standard says.
- **The scale can send without being asked.** `R` and `S` repeat the weight until the next command.
  The profile gives the repeat interval, because the standard says "continuously" and every model
  picks its own rate.
- **Zero and tare refusals become protocol status.** Refusing to zero or tare an unsettled reading
  is already the scale's behaviour; over SMA it appears as the zero-error and tare-error indicators
  with a dashed weight field, which is how a real scale reports it.
- **No existing profile changes.** `ScaleProfile` becomes a union discriminated by `protocol`, but
  a `toledo8217` profile keeps exactly the keys it has today, in the same place, so
  `toledo8217-15kg` and every user-provided Toledo profile load unchanged. What the union adds is
  that a profile carrying another protocol's settings is a validation error naming the key, instead
  of being silently ignored. The new keys belong to `sma` profiles, which nobody has yet.

Not in this change:

- **NCI.** Issue #21 names "NCI and its SMA variant", but they are two protocols, and only SMA has a
  standard we can cite. NCI needs its own document and its own issue.
- **Multi-range scales.** The standard has a range indicator and multi-range capacity reporting; a
  single range is reported, `1`, as every built-in profile is single-range.
- **The communication-error reply `!`.** It answers a parity or framing error, which the simulator
  cannot see: a serial framing mismatch is detected and reported by the connection layer instead.

## Capabilities

### New Capabilities

None. The SMA protocol is behaviour of the existing scale.

### Modified Capabilities

- `weight-scale`: new requirements for the SMA framing, each command group, the unit of measure,
  continuous weight, the About and Information dialogues, and unknown commands. The existing
  "Zero and tare" requirement changes: refusing an unsettled zero or tare is now also reportable on
  the wire. The Toledo requirements are unchanged in behaviour.
- `configuration`: a scale profile's settings belong to the protocol it names. An `sma` profile
  defines the `units` list, the About fields (maker, model, revision, serial number) and the repeat
  interval; a `toledo8217` profile keeps the reply formatting it has today, unchanged.
- `control-api`: the scale state gains the current unit, so a test can read what the scale would
  report without speaking the protocol.

## Impact

- `src/emupos/scale/sma/sma.py`: the new protocol, beside `toledo8217/`.
- `src/emupos/scale/scale.py`: the protocol seam (actions applied by the scale), the current unit,
  and the timer that drives continuous weight.
- `src/emupos/scale/weights.py`: converting grams to a unit's text, and the count-by rounding that
  `kilograms()` does for Toledo today.
- `src/emupos/config.py`: `ScaleProfile` per-protocol settings, the `units` list, About fields.
- `src/emupos/profiles/scales/`: the reshaped `toledo8217-15kg`, and a new SMA profile.
- `src/emupos/api/`: the `unit` field in the scale state and the OpenAPI document.
- `docs/protocols/sma.md`, `docs/configuration.md`, `docs/automation.md` if the state is documented
  there, and `README.md` where the supported protocols are listed.
- Tests: a dialogue suite for the new protocol mirroring `toledo8217/test_toledo8217.py`, profile
  validation, and the reshaped profile in every test that builds one.
