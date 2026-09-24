## 1. Profile shape

- [x] 1.1 In `config.py`, split `ScaleProfile` into a base with the shared fields (`type`, `name`, `protocol`, `capacity_grams`, `division_grams`, `settle_ms`, `serial`) and two members discriminated by `protocol`: `Toledo8217Profile` with `reply_integer_digits` and `reply_decimals`, and `SmaProfile` with `units`, `maker`, `model`, `revision`, `serial_number` (all `AsciiText`) and `repeat_interval_ms` (design D8).
- [x] 1.2 Add a `ScaleUnit` model: `unit` (exactly three characters from the standard's list), `decimals` (≥ 0) and `count_by` (≥ 1, in the last decimal place, as the standard's CAP field gives it). `units` is a non-empty list; reject a repeated unit.
- [x] 1.3 Leave `src/emupos/profiles/scales/toledo8217-15kg.yaml` as it is: the Toledo member of the union keeps the same keys in the same place. Add a test that loads the file as it stands today, so a later refactor cannot quietly change the shape users write.
- [x] 1.4 Add `src/emupos/profiles/scales/sma-15kg.yaml`: 15000 g capacity, 5 g division, units kilograms (3 decimals, count-by 5) then pounds (2 decimals, count-by 1), About fields for a generic simulated scale, 200 ms repeat interval, serial 9600 8N1. Cite SMA SCP-0499 in a comment as the Toledo profile cites its source.
- [x] 1.5 Add `test_config.py` cases for an `sma` profile, for a profile whose settings belong to the other protocol, and for a duplicate unit; check `emupos config validate` on the starter and demo configurations. Existing scale-profile tests should need no edit — if one does, the union changed a shape it should not have.

## 2. The protocol seam

- [x] 2.1 In `scale.py`, define the operations interface a protocol receives — `state()`, `zero()`, `tare(grams=None)`, `clear_tare()`, `select_unit(unit)` — where `zero` and `tare` return whether the scale accepted the operation rather than raising (design D1). `Scale` implements it and keeps publishing `scale.weight.changed` for each accepted operation.
- [x] 2.2 Change the protocol call from `receive(data, state)` to a form that takes the operations interface, and move `Toledo8217` onto it unchanged: it only reads `state()`.
- [x] 2.3 Hold the current unit on `Scale`, from the profile's first unit, with `select_unit` returning whether the unit is listed. A Toledo profile has no units and reports none.
- [x] 2.4 Let a protocol ask to be woken: extend `next_deadline()` and `tick()` so a protocol with a due repeat is written to its connection (design D5).

## 3. Weight formatting

- [x] 3.1 In `weights.py`, convert grams to a unit as `Decimal` with exact factors (1 lb = 453.59237 g, 1 oz = 28.349523125 g), round to the unit's count-by with halves away from zero, and format with the unit's decimals, right-justified in 10 characters (design D3).
- [x] 3.2 Add the inverse for a preset tare: a weight in the current unit to whole grams.
- [x] 3.3 Unit-test the conversions at boundaries: 0 g, one count-by, a half count-by rounding away from zero, a weight needing all 10 characters, and a negative weight.

## 4. The SMA protocol

- [x] 4.1 `scale/sma/sma.py`: the frame parser — LF to CR, bytes outside a frame discarded, ESC acted on byte by byte before framing (design D7), a frame split across reads answered as one.
- [x] 4.2 The standard reply: status, range, gross/net, motion, reserved, weight field, unit. Centre dashes for the error cases (design D4).
- [x] 4.3 Weighing: `W`, `H` (ten times the resolution, lower-case gross/net), `P` and `Q`.
- [x] 4.4 Zero and tare: `Z`, `T`, `T<weight>`, `M`, `C`, each applied before the reply is formed, with the zero-error and tare-error indicators for a refusal, the tare error cleared after one reply.
- [x] 4.5 Units: `U` cycles, `U<uuu>` selects, an unlisted unit is ignored.
- [x] 4.6 Continuous weight: `R` and `S` repeat at the profile's interval to the connection that asked, stopped by any further command from it.
- [x] 4.7 Diagnostics `D`, and the About (`A`, `B`) and Information (`I`, `N`) dialogues with a pointer per connection, the `CAP` line and `CMD` list derived from the profile and the implemented commands (design D6).
- [x] 4.8 `X` and every unrecognised command answer `<LF>?<CR>`.
- [x] 4.9 Register `"sma"` in `PROTOCOLS`.

## 5. Control API

- [x] 5.1 Add `unit` to the scale state in `api/schemas.py` and the device description, null for a protocol without units.
- [x] 5.2 Regenerate `docs/api/openapi-v1.json` and check the contracts test.

## 6. Tests

- [x] 6.1 `scale/sma/test_sma.py`: a dialogue test per command group, in the style of `toledo8217/test_toledo8217.py`, asserting exact bytes.
- [x] 6.2 Framing: a command split across reads, bytes outside a frame, ESC during a partial frame and during a repeat.
- [x] 6.3 Zero and tare through the protocol publish `scale.weight.changed`, and refusals leave the state unchanged.
- [x] 6.4 Continuous weight: repeats arrive at the interval, follow the weight, stop at the next command, and go to one connection only.
- [x] 6.5 About and Information: full dialogues, the pointer per connection, and `B`/`N` past the end.
- [x] 6.6 A test that the Toledo dialogues are byte-for-byte unchanged after the seam change.
- [x] 6.7 Run the full suite, `ruff` and `pyright`.

## 7. Documentation

- [x] 7.1 `docs/protocols/sma.md`: the framing, the commands, the status characters, the units and the profile settings, written in our own words and citing SMA SCP-0499 with the archive link.
- [x] 7.2 `docs/configuration.md`: the scale profile keys per protocol.
- [x] 7.3 `README.md` and `docs/README.md` where the simulated protocols are listed.
- [x] 7.4 Keep the commit and PR free of a breaking-change marker: no existing profile or API changes, so this is a `feat(scale):` and the release stays on a minor bump.
- [x] 7.5 Update the `weight-scale` spec's Purpose line, which names only the Toledo protocol, and archive the change with `openspec archive speak-the-sma-scale-protocol` in the implementation commit.
- [ ] 7.6 Comment on #21 that SMA is implemented and NCI still needs a public document, so the issue can be split or closed.
