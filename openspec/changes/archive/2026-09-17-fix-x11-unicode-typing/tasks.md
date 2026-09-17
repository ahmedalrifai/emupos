## 1. Checklist recipe

- [x] 1.1 In `docs/keyboard-scanning-checklist.md`, import `plan_keys` from `emupos.scanner.keys`. Run the Docker recipe exactly as written in `python:3.13-slim`: `xev` prints key codes 50, 38, 56, 10, 20 and 36.

## 2. Scan steps on the keyboard

- [x] 2.1 Add `start_scan(keys)` and `end_scan()` to the `Keyboard` protocol in `keyboard.py`. `type_keys` calls `start_scan` before the first key and `end_scan` in a `finally` (design D4).
- [x] 2.2 Add empty `start_scan` and `end_scan` to `MacKeyboard` and `WindowsKeyboard`, and recording versions to `FakeKeyboard` in `test_keyboard.py`.
- [x] 2.3 In `test_keyboard.py`, test that `start_scan` receives the scan's keys before the first press, and that `end_scan` runs after the last press, after a refused key, and when the typing task is cancelled.

## 3. X11 Unicode typing

- [x] 3.1 In `x11.py`, bind each spare key code as two equal keysyms with a width of 2 (design D1).
- [x] 3.2 Load libxkbcommon (`libxkbcommon.so.0`) through `ctypes` for `xkb_keysym_to_utf32`, and treat a missing library as "no layout keys". Add `XkbGetState` and `XkbLockModifiers` to the libX11 signatures.
- [x] 3.3 Add the layout key lookup (design D2):
  - build a map from character to (key code, level) from the active group's first and Shift levels in the core keymap;
  - skip keypad keysyms, emupos's own spare key codes, and groups beyond the second;
  - the first level wins over the Shift level;
  - `press` types a found character with its key, and with Shift for the Shift level.
- [x] 3.4 Replace `_find_unused_keycode` with `_find_unused_keycodes`, which returns every key code without keysyms. Keep a least-recently-used map from missing character to spare key code:
  - reuse a bound character without rebinding;
  - otherwise take a free key code, highest first;
  - when none is free, take the least recently used character's key code;
  - return `None` when there is no free key code and nothing is bound.

  (design D2)
- [x] 3.5 In `X11Keyboard.start_scan`, for a scan with Unicode characters:
  1. unlock Caps Lock if it is locked and no other scan is open (design D3);
  2. if a bound key code lost its keysym (keymap reloaded), forget the bindings and list the free key codes again;
  3. run the layout key lookup;
  4. bind every missing character before the first key, stopping when no free key code is left, then sync (design D2).
- [x] 3.6 In `X11Keyboard.end_scan`, lock Caps Lock again once no scan is open, if `start_scan` unlocked it (design D3).
- [x] 3.7 Add `_unbind_all`, which rebinds every spare key code to `NoSymbol` and syncs. Register it with `atexit` in `check_ready` once the display is open (design D5).
- [x] 3.8 In `test_x11.py`, test with fake libX11, libXtst and libxkbcommon everything listed in design D7.
- [x] 3.9 Update the `--unicode` section of `docs/linux-x11.md`:
  - **How characters are typed:** with the active layout's keys (carrying the key's position, with Shift where needed); other characters with spare key codes. This needs libxkbcommon (`libxkbcommon0` on Debian and Ubuntu, `libxkbcommon` on Fedora); without it, every character uses a spare key code.
  - **The limit:** more different missing characters than unused key codes (19 on Xvfb) reuses the least recently used key code, which an app that is far behind can misread.
  - **Caps Lock:** turned off during a `--unicode` scan and turned back on afterwards.
  - **Releasing key codes:** spare key codes are released when emupos stops with Ctrl+C or SIGTERM. A killed emupos leaves them bound until `setxkbmap` or a new login.

## 4. Verification

Run these in Xvfb with `xev -root -event keyboard` as the app. To pause the app, stop `xev` with `SIGSTOP` and resume it with `SIGCONT`. Each check runs three times and counts only if every run passes. All scans use `unicode` true unless stated.

- [x] 4.1 At 10 ms with the app running, all exact:
  - `ABC123` and `AaZz!9` under `us`, `ara` and `fr`;
  - `كود-42` under `us` and `ara`;
  - `Ab1-` with `unicode` false, unchanged from `8fc149a`.
- [x] 4.2 Layout keys, all exact:
  - `كود-42` under `ara` at 0 ms, binding no spare key code;
  - 62 letters and digits under `us` at 0 ms with the app running, and at 10 ms with the app paused for the whole scan, binding no spare key code;
  - 28 Arabic letters under `ara` with the app paused.
  - Under `us,ara`, with each group active in turn: `كود-42` and `abc123` with the app paused.
  - A second scan of `éü`, `ÉÜß` or `كود-42é` in the same process binds nothing. After `setxkbmap us` between the two scans, the characters are bound again and arrive exactly.
- [x] 4.3 Spare key codes: `كود-42` and 19 different Arabic letters under `us` are exact at 0 ms with the app running, and at 0 ms and 10 ms with the app paused for the whole scan.
- [x] 4.4 With Caps Lock on (XTest key code 66), and Caps Lock still on after each scan:
  - `abc123`, `AaZz!9` and `abcABC` under `us` arrive exactly, with the app running and with it paused, at 10 ms and 0 ms;
  - `abc123` with `unicode` false arrives as `ABC123`.
- [x] 4.5 Without libxkbcommon (the library removed from the container), `كود-42` under `ara` and `AaZz!9` under `us` arrive exactly, using spare key codes.
- [x] 4.6 28 Arabic letters under `us` at 10 ms with the app paused for the whole scan: only the first 9 characters are wrong. This documents the limit rather than hiding it.
- [x] 4.7 With the real `emupos run`, count the unused key codes (`xmodmap -pke`) before a `--unicode` scan of `كود-42é` under `us` and after stopping. Ctrl+C and SIGTERM return to the starting count; SIGKILL does not, and `setxkbmap` restores it.
- [x] 4.8 `uv run ruff check`, `uv run ruff format --check`, `uv run pyright` and `uv run pytest` all pass.
- [x] 4.9 Add these Linux checks, which need a desktop, to `docs/keyboard-scanning-checklist.md`:
  - `--unicode` of `abc123` with Caps Lock on, into gedit and the browser;
  - the key logger's `code` values for `--unicode` of `كود-42` with the Arabic layout active (expected: the Arabic layout's key positions).

## 5. Waiting before a reuse, and cleanup after a kill

- [x] 5.1 Add `async prepare_key(key)` to the `Keyboard` protocol. `type_keys` awaits it before each key, after the inter-key delay. Add empty versions to `MacKeyboard` and `WindowsKeyboard`, a recording one to `FakeKeyboard`, and update `test_keyboard.py` (design D4).
- [x] 5.2 Add `KeymapWatch`, which records emupos's keymap changes and other clients' keymap reads through X RECORD on a second connection, started before the first spare key code is bound (design D2).
- [x] 5.3 In `X11Keyboard.prepare_key`, before a reuse, wait for the app (design D2):
  - wait until the focused client has read the keymap after emupos's latest change, then `READ_GRACE_S` (20 ms);
  - without RECORD or a focused client, wait until the reused key code's character was pressed `REUSE_WAIT_S` (2 s) ago;
  - wait `REUSE_WAIT_S` at most per scan, asynchronously.
- [x] 5.4 In `check_ready`, intern a uniquely named atom and own its selection with a 1×1 window, then clear the bindings of killed emupos processes (design D6). Keep the root property of that name in step with the bindings, and delete it at exit.
- [x] 5.5 In `test_x11.py`, test the wait, the per-scan budget, the timed fallback, `KeymapWatch`, and the cleanup after a kill (design D7).
- [x] 5.6 Update `docs/linux-x11.md` (the wait and its 2-second limit, cleanup after a kill), and add to the checklist: 28 Arabic letters under US into gedit and the browser, and the key code count around a `kill -9`.
- [x] 5.7 In Xvfb, with `xev` as a focused window, three runs each, all exact:
  - 28 Arabic letters under `us` at 10 ms and 0 ms with the app running;
  - the same, with the app resuming 500 ms, 800 ms and 1500 ms after typing starts;
  - 52 Arabic and Greek letters at 0 ms, and at 10 ms with the app resuming after 1000 ms;
  - 28 Arabic letters with no focused app (timed wait) and the app resuming after 500 ms.

  With the app paused for the whole scan, exactly the first 9 are wrong after the 2-second budget.
- [x] 5.8 With real `emupos run` processes, three runs each:
  - a killed emupos's key codes are free again after the next emupos's first scan;
  - a running emupos's key codes are left alone, and cleared by a later emupos once it is killed;
  - a key code rebound to F13 after the kill keeps F13.
- [x] 5.9 Rerun sections 1 and 4 on the final code; `uv run ruff check`, `uv run ruff format --check`, `uv run pyright` and `uv run pytest` pass.
