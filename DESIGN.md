---
name: emupos
description: A quiet, light device dashboard for driving simulated point-of-sale hardware by hand.
colors:
  page-grey: "#f4f5f7"
  card-white: "#ffffff"
  hairline: "#e4e7ec"
  row-line: "#f0f2f5"
  control-edge: "#d0d5dd"
  quiet-fill: "#f2f4f7"
  wash: "#f9fafb"
  ink: "#111827"
  ink-2: "#4b5563"
  ink-3: "#6b7280"
  action-blue: "#2563eb"
  action-blue-deep: "#1d4ed8"
  blue-tint: "#eff4ff"
  blue-note-ink: "#1e40af"
  fault-red: "#dc2626"
  fault-red-ink: "#991b1b"
  fault-red-tint: "#fef2f2"
  ready-green: "#15803d"
  ready-green-tint: "#ecfdf3"
  moving-amber: "#b45309"
  moving-amber-tint: "#fffbeb"
typography:
  headline:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "40px"
    fontWeight: 650
    lineHeight: 1
    letterSpacing: "-0.02em"
    fontFeature: "tnum"
  title:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "16px"
    fontWeight: 650
    lineHeight: 1.2
  body:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "12.5px"
    fontWeight: 600
    lineHeight: 1.2
  data:
    fontFamily: "ui-monospace, SF Mono, Menlo, Consolas, monospace"
    fontSize: "12.5px"
    fontWeight: 500
    lineHeight: 1.4
rounded:
  control: "8px"
  tile: "10px"
  card: "12px"
  full: "999px"
spacing:
  xs: "6px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
components:
  card:
    backgroundColor: "{colors.card-white}"
    rounded: "{rounded.card}"
    padding: "16px"
  button-primary:
    backgroundColor: "{colors.action-blue}"
    textColor: "{colors.card-white}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
    height: "36px"
  button-primary-hover:
    backgroundColor: "{colors.action-blue-deep}"
  button-secondary:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
    height: "36px"
  button-secondary-hover:
    backgroundColor: "{colors.wash}"
  button-disabled:
    backgroundColor: "{colors.quiet-fill}"
    textColor: "#98a2b3"
  input:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "6px 10px"
    height: "36px"
  pill-neutral:
    backgroundColor: "{colors.quiet-fill}"
    textColor: "{colors.ink-2}"
    typography: "{typography.label}"
    rounded: "{rounded.full}"
    padding: "5px 10px"
  pill-ready:
    backgroundColor: "{colors.ready-green-tint}"
    textColor: "{colors.ready-green}"
  pill-fault:
    backgroundColor: "{colors.fault-red-tint}"
    textColor: "{colors.fault-red}"
  pill-moving:
    backgroundColor: "{colors.moving-amber-tint}"
    textColor: "{colors.moving-amber}"
  chip:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.full}"
    padding: "5px 12px"
    height: "30px"
  chip-selected:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.card-white}"
  icon-tile:
    backgroundColor: "{colors.blue-tint}"
    textColor: "{colors.action-blue}"
    rounded: "{rounded.tile}"
    size: "38px"
  stat:
    backgroundColor: "{colors.wash}"
    rounded: "{rounded.control}"
    padding: "8px 10px"
---

# Design System: emupos

## Overview

**Creative North Star: "The Quiet Bench"**

A device dashboard played straight: each simulated device is one white card on a pale grey page, carrying its state in one line and its physical actions below. The page sits in a narrow window beside the POS app, so it stays light, calm and dense without being cramped. Colour means something or is absent: blue is the one action colour, and green, red and amber appear only as state.

The system refuses costume. Devices are not drawn as hardware, there is no sidebar and no chart; the only picture on the page is the receipt the printer actually produced, shown as a strip of paper. Everything else is type, hairlines and a small set of controls.

**Key Characteristics:**
- Light only: white cards (1px hairline, 12px corners, faint shadow) on a grey page.
- One action colour (blue) for primary buttons, links, focus and the caret.
- Semantic status pills with a leading dot: green ready, red fault, amber open or moving, grey neutral.
- System UI stack for the interface; monospace only for data (addresses, times, event types, payloads, scans).
- Hand-drawn 1.75-stroke line icons in soft blue tiles, one per device type.
- Faults are switches, not checkboxes or buttons.

## Colors

Cool neutral greys with one blue for action and three semantic hues that only ever report state.

### Primary
- **Action Blue** (`action-blue`): primary buttons, link buttons, the focus ring, the text caret, checkbox accent, and the icon inside each device tile. Deepens to **Action Blue Deep** on hover.
- **Blue Tint** (`blue-tint`): the icon tile ground and the countdown banner ground, paired with **Blue Note Ink** (`blue-note-ink`) for banner text.

### Secondary (semantic state)
- **Ready Green** (`ready-green` on `ready-green-tint`): ready, connected and stable readings.
- **Fault Red** (`fault-red` on `fault-red-tint`): active faults, the "on" state of a fault switch, a lost connection. Alert text uses the darker **Fault Red Ink** (`fault-red-ink`) on the same tint.
- **Moving Amber** (`moving-amber` on `moving-amber-tint`): a drawer that is open, a scale reading still moving.

### Neutral
- **Page Grey** (`page-grey`): the page behind the cards, and the scrollbar track.
- **Card White** (`card-white`): cards, inputs, secondary buttons, unselected chips, the top bar (at 94% opacity).
- **Hairline** (`hairline`): card borders, card dividers, the top bar's bottom edge, table header rule. **Row Line** (`row-line`) is the lighter rule between event rows.
- **Control Edge** (`control-edge`): the border of every interactive control (inputs, secondary buttons, chips) and the off track of a switch.
- **Quiet Fill** (`quiet-fill`) and **Wash** (`wash`): the neutral pill and disabled button ground; the stat tiles, table header and secondary-button hover.
- **Ink / Ink 2 / Ink 3** (`ink`, `ink-2`, `ink-3`): headings and values; labels and secondary copy; metadata, units, hints, placeholders and timestamps.

### Named Rules
**The State-Only Hue Rule.** Green, red and amber appear only as state (pills, the fault switch, alerts). They never decorate, and a colour never carries meaning alone: every pill also says its state in words.

**The One Blue Rule.** Blue is the only action colour. A control that is not blue is secondary, and a blue element is always something you can press or where focus is.

## Typography

**Interface Font:** system-ui (with -apple-system, Segoe UI, Roboto, sans-serif)
**Data Font:** ui-monospace (with SF Mono, Menlo, Consolas, monospace)

**Character:** The platform's own UI face, so the page reads like a native tool beside the POS; monospace marks anything that came from a device or the API, never interface copy.

### Hierarchy
- **Headline** (650, 40px, line-height 1, tabular figures): the scale's net weight, the one large reading on the page.
- **Title** (650, 16px, 1.2): card headings (the device id, "Events"). The wordmark is the same size at 700.
- **Body** (400, 14px, 1.5): switch names, inputs, empty states. Secondary copy steps down to 13px (hints, alerts, chips, table).
- **Label** (600, 12.5px, 1.2): field and row labels ("Faults", "Cash drawer", "Last scan"), pills.
- **Data** (monospace 500, 12.5px, 1.4): API address, device metadata, event time and type; payloads at 400. The last scan is data at 600, 20px.

### Named Rules
**The Monospace Is Data Rule.** Monospace is reserved for values from devices or the API. Interface copy, labels and buttons are always the UI face.

**The Tabular Figures Rule.** Every changing number (weights, stats, times, countdown, inputs) uses tabular figures so readings do not jitter as they update.

## Layout

A sticky top bar (wordmark, "Control page", API address pushed right, connection pill) over a centred column capped at 1240px with 20px padding and 20px gaps. Device cards sit in an auto-fill grid of columns at least 320px wide with 16px gaps; each device type gets its own column group, so two devices of one kind stack instead of leaving a hole. The events card spans the full width after the grid, its table scrolling inside a 420px window under a sticky header.

Inside a card: header at 16px sides (16px top, 12px bottom), body at 16px with 14px between blocks; dividers run edge to edge across the card. Controls sit in wrapping rows with 8px gaps.

At 640px and below the subtitle drops, outer padding tightens to 12px, and event rows become two-line blocks (time, device and type on the first line, data on the second) instead of losing columns.

## Elevation & Depth

Flat, with borders doing the structural work. Shadows are faint and ambient, never offset or coloured. The receipt image is the one element lifted slightly more, so it reads as paper resting on the card.

### Shadow Vocabulary
- **Rest** (`box-shadow: 0 1px 2px rgba(16, 24, 40, 0.05)`): cards, inputs, secondary buttons.
- **Paper** (`box-shadow: 0 1px 3px rgba(16, 24, 40, 0.16), 0 0 0 1px rgba(16, 24, 40, 0.04)`): the latest receipt image.
- **Knob** (`box-shadow: 0 1px 2px rgba(16, 24, 40, 0.2)`): the white thumb of a switch.
- **Focus halo** (`box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.18)`): an input while focused, with a blue border.

### Named Rules
**The Border First Rule.** Structure comes from 1px hairlines; shadows only soften edges and never exceed the Paper value.

## Shapes

Softly rounded rectangles scaled to the element: 8px for controls, stat tiles and messages; 10px for icon tiles; 12px for cards; fully round for pills, chips, switch tracks and status dots. The receipt image keeps square corners, as paper does.

## Components

### Buttons
- **Shape:** gently rounded (8px), at least 36px tall, 600 weight at 13.5px.
- **Primary:** Action Blue with white text, 8px 14px padding; hover deepens to Action Blue Deep over 0.12s.
- **Secondary:** white with a Control Edge border, ink text and the Rest shadow; hover to Wash.
- **Disabled:** Quiet Fill ground, muted grey text, no shadow, not-allowed cursor. A busy control drops to 65% opacity with a progress cursor.
- **Link button:** blue 600 text with no chrome; underlines on hover (offset 3px). Used for "View full receipt".

### Chips
- **Style:** fully round, 30px tall, white with a Control Edge border, 500 weight at 13px.
- **State:** the selected filter inverts to an Ink ground with white text (`aria-pressed`).

### Status Pills
- **Style:** fully round, Label type, a 7px dot in the current colour ahead of the words.
- **State:** ready (green), fault (red), moving or open (amber), neutral (grey). A plain pill drops the dot for non-state tags such as the scanner mode.

### Cards / Containers
- **Corner Style:** 12px.
- **Background:** Card White on Page Grey.
- **Shadow Strategy:** Rest (see Elevation & Depth).
- **Border:** 1px Hairline.
- **Internal Padding:** 16px; header row holds the icon tile, title with a 12.5px subtitle, and the status pill pushed right.
- **Stat tiles:** Wash ground, 8px corners, 8px 10px padding, a 12px Ink 3 term over a 600 14px value, three across.

### Inputs / Fields
- **Style:** white, 1px Control Edge border, 8px corners, 36px tall, Rest shadow; a unit suffix sits inside in Ink 3.
- **Focus:** border turns Action Blue with the Focus halo. All other focusable elements get a 2px blue outline at 2px offset.
- **Checkboxes:** native, 16px, Action Blue accent.

### Fault Switch (signature)
A full-width row button with the fault name left and a 36 by 20px track right. Off: Control Edge track. On: Fault Red track with the white knob slid 16px. Track and knob transition over 0.15s ease-out; hover dims the track slightly.

### Messages
- **Alert:** Fault Red Tint ground, Fault Red Ink text, 8px corners, 10px 12px padding; the API's message in bold, its fix beneath.
- **Info banner:** Blue Tint ground, Blue Note Ink text, a 700 22px tabular countdown number leading the copy.
- **Hint:** 13px Ink 3 text; inline commands in 12.5px monospace Ink 2.

### Latest Receipt (signature)
The printer's own PNG at full card width on white with the Paper shadow, clipped to 180px and faded out at the bottom when longer; "View full receipt" expands it.

### Events Table
13px rows with 9px 16px cells over Row Line rules; header on Wash in 600 12px Ink 3, sticky. A newly arrived row flashes a pale blue and fades over 1.6s. Reduced-motion users get no transitions or animations.

## Do's and Don'ts

### Do:
- **Do** give each device one card: icon tile, id as title, type as subtitle, status pill right, actions below.
- **Do** use a switch for any on/off device condition, turning Fault Red when on.
- **Do** keep monospace for device and API data only, and set it `dir="auto"` so right-to-left data renders correctly.
- **Do** keep every state in words as well as colour, and every focusable element on the 2px blue focus ring.
- **Do** draw icons as inline 24px line SVGs at 1.75 stroke, round caps and joins, in a Blue Tint tile.

### Don't:
- **Don't** introduce a second action colour; blue is the only one.
- **Don't** use green, red or amber for anything but state.
- **Don't** draw devices as hardware, add a sidebar, or add charts.
- **Don't** add a dark theme; the page is light only.
- **Don't** load fonts, icons or scripts from another origin; the system stacks are the type.
