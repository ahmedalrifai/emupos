---
version: 1
slug: "src-emupos-api-page-index-html"
primary_target: "src/emupos/api/page/index.html"
related_targets: []
---

# Control page

Mode: Operate. One page at `/`, served by `emupos run --ui` (OpenSpec change `serve-a-control-page`).

Audience and job: a POS developer at their desk, the page in a narrow window beside the POS app, testing by hand and sometimes demoing; the page replaces the second terminal. Success: no `emupos` command typed during exploratory testing or a demo.

Proof and content: the configured devices, their live state, the latest receipt image per printer, every event since the page connected. Every action goes through `/api/v1`; refusals show the API's `message` and `fix` verbatim.

Constraints: plain HTML/CSS/JS in three packaged files; nothing from another origin; CSP `default-src 'self'` (no inline styles, no inline script); device data as text only, `dir="auto"`; WCAG AA contrast, switches as switches, focus rings, live regions for countdown and connection. Light only (office scene beside a bright POS). No invented logo: the wordmark is the text "emupos".

Reference: the category-standard concept locked in the 2026-09-21 direction round (kept locally with the other decision-round pages, not in the repository). Build path: code-led (no image generation).

## Direction contract

THESIS: the category standard played straight: a quiet device dashboard where each device is one card with its state and its physical actions, done at the finish of the best operator dashboards. It refuses costume: no hardware skeuomorphism, no sidebar, no charts.

OWN-WORLD: light. White cards (12px radius, 1px #e4e7ec border, faint shadow) on #f4f5f7; ink #111827 / #4b5563 / #6b7280; blue #2563eb for primary actions, links and focus; semantic pills: green ready/stable, red faults, amber drawer open or reading moving, neutral grey. System UI stack; monospace only for data. Hand-drawn 1.75-stroke SVG icons in soft blue tiles. Switches for faults.

STORY: the developer glances at the page and sees each device's state in one line; clicks a switch, a button or types a weight and the card changes when the event arrives; a refusal explains itself inline with its fix; the latest receipt and the events table show what the POS just did.

FIRST VIEWPORT: top bar (wordmark "emupos", "Control page", API address, connection pill). Beneath, a responsive grid of device cards, one column below ~700px: printer card first (status pill, four fault switches, drawer row with Close drawer, latest receipt thumbnail with View full receipt), then the scale (net weight large, tare/gross/capacity, grams input with Set weight, moving checkbox, Zero/Tare), then the scanner (last scan, data input with Scan, exact characters, countdown banner). The events card with device filter chips and the table follows the grid.

FORM: the category standard (canon card), chosen over the dealt hand; seed key 74663844.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
