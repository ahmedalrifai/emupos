## Context

On X11, emupos types a `--unicode` character by binding its keysym to an unused key code with `XChangeKeyboardMapping`, then pressing that key code with XTest, as `xdotool type` does (`src/emupos/transports/keyboard/x11.py`). Today it uses one spare key code for every character: it rebinds the code before each key and never releases it.

All results below come from Xvfb in a `python:3.13-slim` container. The listening app was `xev -root -event keyboard`, and a "paused" app was stopped with `SIGSTOP` and resumed with `SIGCONT`. Xvfb has 19 unused key codes. Browsers and GTK apps were not tested.

**Current code (`8fc149a`):**

| Scan (`unicode` true) | Delay | App | Keysyms received |
|---|---|---|---|
| `ABC123` | 10 ms | running | `a b c 1 2 3 Return` |
| `AaZz!9` | 10 ms | running | `a a z z exclam 9 Return` |
| `كود-42` | 10 ms | running | correct |
| `كود-42` | 0 ms | running | wrong in every run, e.g. `U0648` ×6 |
| `كود-42` | 10 ms and 50 ms | paused during the scan | `2 2 2 2 2 2 Return` |

Three runs of `--unicode` in separate processes reduced the unused key codes from 19 to 16. Scans with `unicode` false were correct in every case.

**Spare key codes only: one per character, both levels (D1), release at exit (D5):**

| Scan (`unicode` true) | Delay | App | Result |
|---|---|---|---|
| 19 different letters | 10 ms | paused for the whole scan | exact |
| 20 different letters | 10 ms | paused | `tbcdef…`: `a` read as `t` |
| 26 different letters | 10 ms | paused | first 7 wrong (`tuvwxyz…`) |
| 26 different letters | 10 ms | resumes 100 or 200 ms after typing starts | exact |
| 26 different letters | 10 ms | resumes 230 / 260 / 300 ms after typing starts | first 1–2 / 3–4 / 6–7 wrong |
| 26 different letters | 10 ms | running | exact |
| `كود-42` | 10 ms | paused | exact |
| 19 different letters | 0 ms | running | characters missing (no keysym) in 6 of 6 runs |
| `كود-42` | 0 ms | running | characters missing in every run |
| `abc123`, Caps Lock on | 10 ms | running | `ABC123` |
| `ABC123` and `كود-42`, Caps Lock on | 10 ms | running | exact |

**The same, with the scan's characters mapped before its first key (D2):**

| Scan (`unicode` true) | Delay | App | Result |
|---|---|---|---|
| 19 different letters | 0 ms | running (with or without a 5 ms pause after mapping) | exact, 12 of 12 |
| `كود-42` | 0 ms | running | exact, 6 of 6 |
| 19 different letters | 0 ms and 10 ms | paused | exact, 12 of 12 |

**Layout keys first, spare key codes for the rest, and Caps Lock off during the scan (D2, D3), one run each:**

| Scan (`unicode` true) | Layout | Delay | App | Spare key codes | Result |
|---|---|---|---|---|---|
| `كود-42` | `ara` | 0 ms | running | 0 | exact |
| `كود-42` | `us` | 0 ms | running | 3 | exact |
| `AaZz!9` | `us`, `fr` | 10 ms | running | 0 | exact |
| `AaZz!9` | `ara` | 10 ms | running | 4 | exact |
| 26 lowercase letters | `us` | 10 ms | paused | 0 | exact (spare key codes only: first 7 wrong) |
| 62 letters and digits | `us` | 10 ms and 0 ms | paused / running | 0 | exact |
| 28 Arabic letters | `ara` | 10 ms | paused | 0 | exact |
| 19 Arabic letters | `us` | 10 ms | paused | 19 | exact |
| 28 Arabic letters | `us` | 10 ms | paused | 19 | first 9 wrong |
| `كود-42`, Arabic group active | `us,ara` | 10 ms | paused | 0 | exact |
| `abc123`, Arabic group active | `us,ara` | 10 ms | paused | 3 | exact |
| `كود-42`, US group active | `us,ara` | 10 ms | paused | 3 | exact |
| `abc123`, Caps Lock on | `us` | 10 ms | running | 0 | exact, Caps Lock on afterwards |
| `AaZz!9`, Caps Lock on | `us` | 10 ms | running and paused | 0 | exact, Caps Lock on afterwards |
| `abcABC`, Caps Lock on | `us` | 0 ms | paused | 0 | exact, Caps Lock on afterwards |
| `abcABC`, Caps Lock on, spare key codes only | `us` | 10 ms | paused | 6 | exact, Caps Lock on afterwards |
| `كود-42`, Caps Lock on | `ara` | 10 ms | running | 0 | exact, Caps Lock on afterwards |

With Caps Lock on, `Ab1-` with `unicode` false came out as `aB1-`, as it would from a real keyboard.

**Stopping a real `emupos run` after a 7-character scan (unused key codes before scan → after scan → after stop), two runs each:**

| Stop | Result |
|---|---|
| Ctrl+C | 19 → 12 → 19 |
| SIGTERM | 19 → 12 → 19 |
| SIGKILL | 19 → 12 → 12 |

Three X11 behaviours explain these results:

- **Case.** When a key code has a single keysym and that keysym is a letter, X reads it as the lowercase letter without Shift and the uppercase letter with Shift.
- **Late readers.** A key event carries only the key code and the modifier state, not a character. The app looks the keysym up when it handles the event, and after a mapping change it reads the server's current keymap.
  - With one shared key code, an app that is behind reads every queued key as the character bound last.
  - With one key code per character, a key is wrong only if its key code was given to another character before the app handled it. That requires both more different characters than unused key codes and an app that is behind by about that many keys: at 10 ms, 200 ms behind was fine and 230 ms was not.
  - Keys of the active layout are never rebound, so they are read correctly however late.
- **Caps Lock.** Xlib turns a looked-up letter into uppercase when Lock is set and the key's type does not use Lock, even if the key has the same keysym on both levels.

At 0 ms, the app sometimes found no keysym for a key code that had been bound before the key was pressed. The exact cause inside Xlib's keymap refresh was not found. Mapping every spare key code before the first key avoided it in every run.

**Reusing a key code only after the app has read the keymap (D2), with the app as a focused `xev` window, three runs each:**

| Scan (`unicode` true, `us` layout) | Delay | App | Result |
|---|---|---|---|
| 28 Arabic letters | 10 ms and 0 ms | running | exact |
| 28 Arabic letters | 10 ms / 0 ms | resumes 500 ms / 800 ms after typing starts | exact |
| 28 Arabic letters | 10 ms | resumes 1500 ms after typing starts | exact (typed in about 1.6 to 1.8 s) |
| 52 Arabic and Greek letters | 0 ms / 10 ms | running / resumes 1000 ms after typing starts | exact (52 letters at 0 ms in about 0.85 s) |
| 28 Arabic letters, no focused app (timed wait) | 10 ms | resumes 500 ms after typing starts | exact (typed in about 2.1 s) |
| 28 Arabic letters | 10 ms | paused for the whole scan | first 9 wrong after the 2 s budget (typed in about 2.4 s) |

A first version reused a key code as soon as the app had read the keymap. At 0 ms, 3 of 6 runs typed the 20th letter as the 1st. The RECORD log showed the app reading the keymap 0.1 ms before emupos changed it again, then never reading it after that change. A change that arrives while Xlib is still handling the keymap reply is dropped, and the app keeps the old character. Waiting 20 ms after the read fixed it: 30 of 30 runs were exact.

**Cleanup after a kill (D6), real `emupos run` processes, three runs each (unused key codes):**

| Scenario | Result |
|---|---|
| A scans `كود-42é`, is killed; B starts and scans once | 19 → 15 leaked → 19 after B's first scan and after B stops |
| A scans, B scans while A runs, A is killed, B stops, C scans | B leaves A's 3 key codes alone; C frees them; 19 at the end |
| A binds `é`, is killed; another program rebinds that key code to F13; B scans | F13 is kept; all other key codes are free |

## Goals / Non-Goals

**Goals:**

- `--unicode` on X11 types exact characters at any delay and for an app that handles the keys late. This includes capital letters and text typed with Caps Lock on, and applies to an app up to 2 seconds behind when key codes must be reused (D2).
- Text the active layout can type needs no keymap changes at all.
- A normally stopped emupos leaves the X keymap and Caps Lock as it found them, and the next emupos clears key codes that a killed one left behind.
- The checklist's Docker recipe runs as written.

**Non-Goals:**

- Characters on a key's AltGr level, or in a layout group other than the active one: they use spare key codes.
- The desktop-only checklist items in #24, and the Linux column of the keyboard-wedge spike.
- Windows and macOS typing behaviour. Both attach the character to the event itself; they only gain empty scan steps (D4).
- Physical-key typing (`unicode` false), which keeps following Caps Lock and the layout as a real scanner does.

## Decisions

### D1. Bind the same keysym on both levels

Bind each spare key code as the two-keysym list `(K, K)` with a width of 2, as xdotool does. The key then types `K` with or without Shift, which fixes `ABC123` → `abc123`. On its own this does not protect against Caps Lock (D3).

- **Alternative: bind `(lower, upper)` and press Shift for capitals.** Rejected: it adds events and still depends on Caps Lock.

### D2. Layout keys first, then one spare key code per missing character, mapped before the first key

**Layout keys.** When a scan with Unicode characters starts:

- Read the core keymap (`XGetKeyboardMapping`) and the active layout group (`XkbGetState`).
- For group *g*, columns *2g* and *2g+1* of each key code hold its first and Shift levels.
- Turn each keysym there into a character with `xkb_keysym_to_utf32` from libxkbcommon, loaded through `ctypes`. This covers both legacy keysyms such as `Arabic_kaf` and Unicode keysyms such as `U0643`.
- Skip:
  - keypad keysyms (`0xFF80`–`0xFFBD`), because their level depends on Num Lock;
  - emupos's own spare key codes;
  - groups beyond the second, which the core keymap does not show.
- The first match wins, first level before Shift level.
- A character found this way is pressed with its key, with Shift for the Shift level, and the keymap is not changed.
- The lookup runs at every scan start, so a layout switch between scans is picked up.

**Spare key codes.** For the characters the layout lacks:

- On the first such scan of the process, list the key codes that have no keysyms.
- Keep a map from character to spare key code, ordered from least to most recently used.
- Before the first key, bind each missing character that is not bound yet, then sync. Stop when no free key code is left.
- During typing, a missing character that is still unbound takes the key code of the least recently used character. This is the only case in which a key code is rebound while keys are being typed, and it waits for the app first (below).
- A repeated character is bound once.
- At each scan start, if a bound key code no longer holds its character's keysym, the keymap was reloaded (for example by `setxkbmap`, which the Linux checklist runs while `emupos run` keeps running). emupos then forgets its bindings and lists the free key codes again.

**Without libxkbcommon.** If the library is not installed, the layout lookup is skipped and every character uses a spare key code.

**Reusing a key code.** A reused key code is only wrong for an app that has not yet handled the key it typed before. Xlib notes a keymap change when it reads the notification from the socket, and fetches the keymap at the next key lookup. A keymap read after emupos's latest change shows that the app has reached that change. The keys sent before the next change are already queued behind it, and the 20 ms that follow give the app time to look them up before the next notification arrives:

- When the first spare key code is needed, emupos starts recording with the X RECORD extension (its client functions are in libXtst) on a second connection. It records emupos's own keymap changes and every client's keymap reads (`GetKeyboardMapping`, and XKB `GetMap`), in the order the server handled them.
- Before a reuse (the new `prepare_key` step, D4), emupos finds the client that owns the focused window. It waits until that client has read the keymap after emupos's latest change, then 20 ms more for Xlib to finish handling the reply.
- Without RECORD, or when no client owns the focus (none, pointer-root, the root window), it waits instead until the key code's previous character was pressed 2 seconds ago.
- A scan waits 2 seconds at most in total. After that, key codes are reused without waiting, so an app that stops handling events for longer can still read a wrong character.

The wait is asynchronous, so the control API stays responsive. Scans that do not reuse a key code never wait.

With this, a scan can only go wrong if it has more than 19 different characters that the active layout lacks (on Xvfb) *and* the app is more than 2 seconds behind. Under `ara`, 28 Arabic letters need no spare key codes at all.

- **Alternative: a minimum delay for Unicode keys.** Rejected: a paused app got wrong characters at 50 ms. No delay is safe for a busy app, and a long one slows every scan. The timed wait above is only the fallback, and only for reuses.
- **Alternative: restore the mapping after each key,** as xdotool does. Rejected: an app that reads late then finds no keysym at all.
- **Alternative: wait until the app has handled the key.** X gives the sender no such acknowledgement, but the app's keymap read is visible through RECORD, and is enough (see above).
- **Alternative: watch every client's reads.** Rejected: panels and the window manager also read the keymap after a change, which would end the wait while the focused app is still behind.
- **Alternative: two characters per spare key code, using Shift for the second.** Tested: this doubles the limit (38 different letters exact with the app paused, 39 not). Rejected: layout keys remove far more of the need, and with this approach 0 ms lost characters in the same way.
- **Alternative: look characters up with `xkb_utf32_to_keysym` and `XKeysymToKeycode`.** Rejected: it returns one keysym per character, while a layout may use the legacy or the Unicode keysym for it. Converting the keymap's keysyms finds both.

### D3. Turn Caps Lock off for a Unicode scan

When a scan with Unicode characters starts, read the locked modifiers (`XkbGetState`). If Caps Lock is locked, unlock it with `XkbLockModifiers` on the core keyboard. When the scan ends, lock it again. xdotool's `--clearmodifiers` does the same.

- Tested: with Caps Lock on, `abc123`, `AaZz!9`, `abcABC` and `كود-42` came out exact, with the app running and paused, at 10 ms and 0 ms, and with layout keys or spare key codes. Caps Lock was on after every scan.
- Scans without Unicode characters do not touch Caps Lock: a real scanner is affected by it.
- When scans overlap, Caps Lock is restored when the last open scan ends.
- **Alternative: document Caps Lock as a limitation.** Rejected: the spec requires exact characters.

### D4. Start-of-scan and end-of-scan steps on the keyboard

Add `start_scan(keys)`, `end_scan()` and `async prepare_key(key)` to the `Keyboard` protocol:

- `type_keys` calls `start_scan` before the first key and `end_scan` in a `finally`, so a cancelled scan also restores Caps Lock. It awaits `prepare_key` before each key, after the inter-key delay.
- X11 does the layout lookup and mapping (D2) and handles Caps Lock (D3) in the scan steps, and waits before reusing a key code (D2) in `prepare_key`.
- The macOS and Windows keyboards implement all three as empty methods.

- **Alternative: keep the protocol and hide the steps in `press`.** Rejected: `press` sees one key at a time, so it cannot map the whole scan first or know when the scan ends.

### D5. Release bound key codes when the process exits

`check_ready` registers an `atexit` handler when it opens the display. The handler rebinds every spare key code emupos bound to `NoSymbol` and syncs. `emupos run` stops through a normal interpreter exit on Ctrl+C and SIGTERM, so the handler runs; this was confirmed with the real daemon (table above).

- **Alternative: release in `end_scan`.** Rejected: an app that handles the scan after it finished would lose the characters, the same failure as in D2.

### D6. The next emupos clears the key codes of a killed one

A killed emupos (SIGKILL, crash) cannot run D5. The next emupos cleans up when it opens the keyboard (`check_ready`, at its first keyboard scan or in `emupos doctor`):

- Each emupos interns an atom with a unique name (`_EMUPOS_KEYCODES_` and a UUID). It creates a 1×1 unmapped window and makes it the owner of the selection with that name. The X server drops the ownership when the connection closes, even on SIGKILL.
- In the root window property of that name, it keeps its current bindings as (key code, keysym) pairs, rewritten after each change and deleted at exit.
- When the next emupos starts, it lists the root properties with that prefix. For each one whose selection has no owner, it unbinds the recorded key codes that still hold the recorded keysym, then deletes the property.
- A running emupos keeps its selection, so its bindings are left alone. A key code that another program changed after the kill no longer holds the recorded keysym, so it is left alone too.
- Each process writes only its own property, so no server lock is needed.

A first prototype used a single shared property, locked the X server for every update, and used the owner's window ID to tell whether it was alive. The window ID failed: a new process can get a dead process's window ID. Unique selection names do not have that problem.

- **Alternative: leave it to `setxkbmap` or a new login.** Rejected: users would need to know about it, and each crash would take more key codes.

### D7. Tests

`test_x11.py` replaces libX11, libXtst and libxkbcommon with fakes that record keymap changes, Caps Lock changes and pressed key codes. It covers:

- **layout keys:**
  - a character on the active group's first or Shift level is pressed with that key, with Shift for the Shift level, and binds nothing;
  - a keypad keysym is not used;
  - the second group is used when it is active;
- **spare key codes:**
  - two equal keysyms for a missing capital letter;
  - all missing characters bound before the first press;
  - no rebinding for a repeated character;
  - reuse of the least recently used key code when none is free;
  - nothing typed when there is no free key code;
  - characters bound again after the keymap was reloaded;
- **without libxkbcommon:** every character uses a spare key code;
- **Caps Lock:** unlocked and relocked only for Unicode scans, and only when it was locked;
- **reusing a key code:**
  - a reuse waits until the focused app has read the keymap;
  - no wait while spare key codes last;
  - a scan waits `REUSE_WAIT_S` at most;
  - without RECORD or a focused app, the timed wait;
- **the RECORD watch** (`KeymapWatch`): emupos's changes and other clients' reads are counted, and other requests are ignored;
- **cleanup after a kill:**
  - a killed emupos's key codes are cleared;
  - a running one's are kept;
  - a key code changed since is left alone;
  - the process's own bindings are listed until exit;
- **release:** all bound key codes are released.

`test_keyboard.py` checks that `type_keys` calls `start_scan` before the first key and `end_scan` after the last, including when a key fails and when the task is cancelled.

CI has no X server, so the Xvfb checks in tasks section 4 are the end-to-end check.

## Risks / Trade-offs

- **More than 19 different characters that the active layout lacks** (on Xvfb) can still produce wrong characters if the app is more than 2 seconds behind. → The limit is stated in `docs/linux-x11.md`. It needs, for example, long Arabic text while a US layout is active, and an app that freezes during the scan.
- **RECORD may be disabled, or the focused window may belong to another client than the one that reads the keys** (an XIM input method server, or a window manager that focuses its frame). → emupos then waits the timed fallback or the 2-second budget, and reuses the key code after that. Browsers and GTK apps are to be checked in the desktop checklist.
- **The 20 ms after an app's keymap read is empirical.** It covers Xlib handling the reply, and the app handling the keys already queued, on a local X server with `xev`. An app with slow handlers that resumes with a long backlog may need more. → The 0 ms and paused checks run three times, and the desktop checklist sends 28 Arabic letters into gedit and a browser. If that check fails, scale the wait with the number of keys pressed since the app's last read. Raising it for every reuse is not an option: 33 reuses × 100 ms would exceed the 2-second budget in the 52-letter case.
- **One atom and one small unmapped window per emupos process.** X never frees atoms. → Accepted: one per process start.
- **libxkbcommon may be missing,** as on a minimal server. Then every character uses a spare key code, and the limit applies to all different characters. → `docs/linux-x11.md` names the package (`libxkbcommon0` on Debian and Ubuntu, `libxkbcommon` on Fedora). GTK and Qt desktops already have it.
- **Characters typed with layout keys look like real key presses.** A capital letter is sent with Shift, and the app sees the key's position. → This matches a real keyboard. The spec and docs state it.
- **A modifier held by the user during the scan** (Shift, AltGr), or a layout switch in the middle of a scan, can change what layout keys type. → Physical-key typing has the same limitation. Scans take well under a second.
- **A killed emupos leaves its spare key codes bound until the next emupos opens the keyboard** (D6). → `docs/linux-x11.md` says so, and names `setxkbmap` for clearing them without emupos.
- **The 0 ms fix is empirical.** Why Xlib missed the bindings is not known. → Tasks 4.2 and 4.3 repeat the 0 ms checks.
- **The Caps Lock light goes off during a Unicode scan.** A Caps Lock press during the scan is overwritten when the scan ends. → Accepted: scans take well under a second.
- **The free key codes are listed once per process.** A key code that another tool, such as xdotool, binds later can be taken over by emupos. → This happens today too, and xdotool reverts its own bindings.
- **Most layout-key results come from one run each.** → Section 4 of the tasks repeats them three times.

## Migration Plan

There is nothing to migrate. To roll back, revert the commit. The behaviour of `unicode` false does not change.

## Open Questions

- How many unused key codes do real Xorg desktops (Ubuntu, Fedora) have? This can be recorded during the desktop checklist in #24.
- What `code` value does a browser report for characters typed with layout keys? This is expected to be the key's position, to be confirmed in the desktop checklist.
- Which client reads the keymap for an app that uses an XIM input method, and does the focused-window rule find it? To be checked on a desktop.
