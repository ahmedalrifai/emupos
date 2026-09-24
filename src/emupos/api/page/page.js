// The emupos control page (control-page spec). It acts only through /api/v1, the same endpoints a
// script uses, and it shows device data as text only: receipt text, scan data and client addresses
// come from whatever connects to a device port, so nothing here is ever inserted as HTML (design D7).

const API = "/api/v1";
const RETRY_MS = 2000;
const COUNTDOWN_S = 3;
const EVENT_LIMIT = 500;
const TYPES = { printer: "Receipt printer", scale: "Weighing scale", scanner: "Barcode scanner" };
const FAULTS = [
  ["paper-near-end", "Paper near end"],
  ["paper-out", "Paper out"],
  ["cover-open", "Cover open"],
  ["offline", "Offline"],
];
const LOOPBACK_FIX = "open the control page through 127.0.0.1, localhost or [::1] on the machine running emupos";

class ApiError extends Error {
  constructor(message, fix = null) {
    super(message);
    this.fix = fix;
  }
}

// --- building blocks ----------------------------------------------------------------------

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === false || value == null) continue;
    node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function icon(type) {
  const svg = document.getElementById("icons").content.querySelector(`[data-icon="${type}"]`);
  return el("span", { class: "icon" }, svg ? svg.cloneNode(true) : null);
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const devicePath = (id) => `/devices/${encodeURIComponent(id)}`;

function kg(grams) {
  const sign = grams < 0 ? "-" : "";
  const abs = Math.abs(grams);
  return `${sign}${Math.floor(abs / 1000)}.${String(abs % 1000).padStart(3, "0")}`;
}

function clock(iso) {
  const d = new Date(iso);
  const pad = (n, width = 2) => String(n).padStart(width, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`;
}

function pairs(data) {
  return Object.entries(data)
    .map(([key, value]) => {
      if (Array.isArray(value)) return `${key}=${value.join(",") || "none"}`;
      return `${key}=${value !== null && typeof value === "object" ? JSON.stringify(value) : value}`;
    })
    .join("  ");
}

function where(device) {
  const connections = device.connections.map((c) => {
    const target = c.device_path && c.device_path !== c.endpoint ? ` → ${c.device_path}` : "";
    return `${c.kind} ${c.endpoint}${target}`;
  });
  return [device.profile, ...connections].filter(Boolean).join(" · ");
}

// --- the API ------------------------------------------------------------------------------

async function call(method, path, body) {
  const init = body === undefined ? { method } : { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  let response;
  try {
    response = await fetch(`${API}${path}`, init);
  } catch {
    throw new ApiError("emupos is not answering", "check that `emupos run --ui` is still running");
  }
  if (response.status === 204) return null;
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const error = payload?.error;
    throw new ApiError(error?.message ?? `the request failed with status ${response.status}`, error?.fix ?? null);
  }
  return payload;
}

function alertBox() {
  const node = el("p", { class: "alert", role: "alert", hidden: true });
  return {
    node,
    show(error) {
      node.replaceChildren(el("b", {}, error.message), error.fix ?? "");
      node.hidden = false;
    },
    clear() {
      node.hidden = true;
    },
  };
}

async function act(button, alert, action) {
  alert.clear();
  button.setAttribute("aria-busy", "true");
  try {
    await action();
  } catch (error) {
    alert.show(error);
  } finally {
    button.removeAttribute("aria-busy");
  }
}

function card(device, pill, body) {
  return el(
    "section",
    { class: "card", "aria-labelledby": `${device.id}-title` },
    el("div", { class: "card-h" }, icon(device.type), el("div", {}, el("h2", { id: `${device.id}-title` }, device.id), el("p", {}, TYPES[device.type])), pill),
    el("div", { class: "card-b" }, body),
  );
}

// --- printer ------------------------------------------------------------------------------

function receiptView(device) {
  const heading = el("div", { class: "receipt-h" });
  const clip = el("div", { class: "clip" });
  const whole = el("button", { type: "button", class: "linkbtn below", "aria-expanded": "false" }, "View full receipt");
  const node = el("div", { class: "receipt" }, heading, clip, whole);
  whole.addEventListener("click", () => {
    const open = !node.classList.contains("whole");
    node.classList.toggle("whole", open);
    whole.setAttribute("aria-expanded", String(open));
    whole.textContent = open ? "Collapse" : "View full receipt";
  });
  function show(id, at) {
    heading.replaceChildren(el("span", { class: "label" }, "Latest receipt"), el("span", { class: "meta" }, `${id} · ${clock(at)}`));
    const src = `${API}${devicePath(device.id)}/receipts/${encodeURIComponent(id)}/image`;
    const image = el("img", { src, alt: `Receipt ${id} printed by ${device.id}` });
    // Only a receipt taller than the preview is cut: it fades out and offers the whole receipt.
    image.addEventListener("load", () => {
      const cut = image.offsetHeight > clip.clientHeight + 1;
      clip.classList.toggle("cut", cut);
      whole.hidden = !cut && !node.classList.contains("whole");
    });
    clip.replaceChildren(image);
  }
  function none() {
    heading.replaceChildren(el("span", { class: "label" }, "Latest receipt"));
    clip.replaceChildren(el("p", { class: "hint" }, `${device.id} has not printed a receipt yet.`));
    whole.hidden = true;
  }
  async function load() {
    try {
      const latest = await call("GET", `${devicePath(device.id)}/receipts/latest`);
      show(latest.id, latest.completed_at);
    } catch {
      none();
    }
  }
  none();
  return { node, show, load };
}

function printerCard(device) {
  const alert = alertBox();
  const pill = el("span", { class: "pill" });
  const drawer = el("span", { class: "pill plain" });
  const switches = FAULTS.map(([fault, name]) => {
    const button = el("button", { type: "button", role: "switch", class: "switch", "aria-checked": "false" }, el("span", {}, name), el("span", { class: "track", "aria-hidden": "true" }));
    button.addEventListener("click", () =>
      act(button, alert, async () => {
        const on = button.getAttribute("aria-checked") !== "true";
        await call(on ? "PUT" : "DELETE", `${devicePath(device.id)}/faults/${fault}`);
        await refresh(device.id);
      }),
    );
    return [fault, button];
  });
  const close = el("button", { type: "button", class: "btn secondary" }, "Close drawer");
  close.addEventListener("click", () =>
    act(close, alert, async () => {
      await call("POST", `${devicePath(device.id)}/drawer/close`);
      await refresh(device.id);
    }),
  );
  const receipt = receiptView(device);
  const node = card(device, pill, [
    el("div", { class: "meta" }, where(device)),
    el(
      "div",
      {},
      el("span", { class: "label above", id: `${device.id}-faults` }, "Faults"),
      el("div", { class: "switches", role: "group", "aria-labelledby": `${device.id}-faults` }, switches.map(([, button]) => button)),
    ),
    el("div", { class: "divider" }),
    el("div", { class: "row" }, el("span", { class: "label" }, "Cash drawer"), drawer),
    close,
    alert.node,
    el("div", { class: "divider" }),
    receipt.node,
  ]);
  return {
    node,
    update(state) {
      const names = FAULTS.filter(([fault]) => state.faults.includes(fault)).map(([, name]) => name);
      pill.className = names.length ? "pill bad" : "pill ok";
      pill.textContent = names.length === 0 ? "Ready" : names.length === 1 ? names[0] : `${names.length} faults`;
      for (const [fault, button] of switches) button.setAttribute("aria-checked", String(state.faults.includes(fault)));
      const open = state.drawer === "open";
      drawer.className = open ? "pill warn" : "pill plain";
      drawer.textContent = open ? "Open" : "Closed";
      close.disabled = !open;
    },
    onEvent(event) {
      if (event.type === "printer.job.completed") receipt.show(event.data.receipt_id, event.at);
    },
    load: receipt.load,
  };
}

// --- scale --------------------------------------------------------------------------------

function scaleCard(device) {
  const alert = alertBox();
  const pill = el("span", { class: "pill" });
  const net = el("b", {});
  const tare = el("dd", {});
  const gross = el("dd", {});
  const capacity = el("dd", {});
  const unit = el("dd", {});
  const stat = (name, value) => el("div", { class: "stat" }, el("dt", {}, name), value);
  // Weights are shown in kilograms whatever the scale reports in, so name the unit the POS reads.
  // A protocol without units (Toledo 8217) reports none, and the stat stays hidden.
  const unitStat = stat("Reporting", unit);
  const grams = el("input", { inputmode: "numeric", autocomplete: "off", placeholder: "1250", "aria-label": `Weight on ${device.id}, in grams` });
  const moving = el("input", { type: "checkbox" });
  const set = el("button", { type: "submit", class: "btn" }, "Set weight");
  const zero = el("button", { type: "button", class: "btn secondary" }, "Zero");
  const tareButton = el("button", { type: "button", class: "btn secondary" }, "Tare");
  const form = el("form", { class: "form" }, el("label", { class: "input" }, grams, el("span", {}, "g")), set);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    act(set, alert, async () => {
      const text = grams.value.trim();
      if (text === "") throw new ApiError("type the weight in grams", "for 1.25 kg, type 1250");
      await call("PUT", `${devicePath(device.id)}/weight`, { grams: Number(text), stable: !moving.checked });
      await refresh(device.id);
    });
  });
  for (const [button, operation] of [[zero, "zero"], [tareButton, "tare"]]) {
    button.addEventListener("click", () =>
      act(button, alert, async () => {
        await call("POST", `${devicePath(device.id)}/${operation}`);
        await refresh(device.id);
      }),
    );
  }
  const node = card(device, pill, [
    el("div", { class: "meta" }, where(device)),
    el("div", { class: "value" }, net, el("span", {}, "kg net")),
    el("dl", { class: "stats" }, stat("Tare", tare), stat("Gross", gross), stat("Capacity", capacity), unitStat),
    el("div", { class: "divider" }),
    form,
    el("label", { class: "check" }, moving, "Reading still moving"),
    el("div", { class: "btns" }, zero, tareButton),
    alert.node,
  ]);
  return {
    node,
    update(state) {
      net.textContent = kg(state.net_grams);
      tare.textContent = `${kg(state.tare_grams)} kg`;
      gross.textContent = `${kg(state.grams)} kg`;
      capacity.textContent = `${state.capacity_grams / 1000} kg`;
      unit.textContent = state.unit ?? "";
      unitStat.hidden = !state.unit;
      const [kind, text] =
        state.grams > state.capacity_grams
          ? ["bad", "Over capacity"]
          : state.net_grams < 0
            ? ["warn", "Under zero"]
            : state.stable
              ? ["ok", "Stable"]
              : ["warn", "In motion"];
      pill.className = `pill ${kind}`;
      pill.textContent = text;
    },
  };
}

// --- scanner ------------------------------------------------------------------------------

function scannerCard(device) {
  const alert = alertBox();
  const state = device.state;
  const keyboard = state.mode === "keyboard";
  const pill = el("span", { class: "pill plain" }, keyboard ? "Keyboard" : "Serial");
  const last = el("div", { class: "last none", dir: "auto" }, "No scan since this page opened.");
  const typedBy = state.typed_by === "client" ? "the client" : "emupos";
  const details = keyboard ? `suffix ${state.suffix} · ${state.inter_key_delay_ms} ms per key · typed by ${typedBy}` : `suffix ${state.suffix}`;
  const body = [
    el("div", { class: "meta" }, [where(device), details].filter(Boolean).join(" · ")),
    el("div", {}, el("span", { class: "label above" }, "Last scan"), last),
    el("div", { class: "divider" }),
  ];
  if (keyboard && state.typed_by === "client") {
    // A browser cannot type into another window: these scans are typed where the POS runs.
    body.push(el("p", { class: "hint" }, "This scanner's keys are typed on the machine with your POS window. Run ", el("code", {}, `emupos scan --device ${device.id} DATA`), " there."));
  } else {
    body.push(...scanForm(device, keyboard, alert));
  }
  body.push(alert.node);
  return {
    node: card(device, pill, body),
    update() {},
    onEvent(event) {
      if (event.type !== "scanner.scan.delivered") return;
      last.className = "last";
      last.textContent = event.data.data;
    },
  };
}

function scanForm(device, keyboard, alert) {
  const data = el("input", { autocomplete: "off", placeholder: "5901234123457", dir: "auto", "aria-label": `Barcode to scan on ${device.id}` });
  const exact = el("input", { type: "checkbox" });
  const go = el("button", { type: "submit", class: "btn" }, "Scan");
  const seconds = el("b", {});
  const countdown = el("p", { class: "info", hidden: true, "aria-live": "assertive" }, seconds, "Click your POS window now. The barcode is typed where the focus is.");
  const form = el("form", { class: "form" }, el("label", { class: "input" }, data), go);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    alert.clear();
    if (data.value === "") {
      alert.show(new ApiError("type the barcode to scan", "for example 5901234123457"));
      return;
    }
    if (keyboard) {
      // The countdown runs here, not in the simulator: a requested scan cannot be cancelled, and
      // the window that would receive the keys is this page (design D6).
      go.disabled = true;
      countdown.hidden = false;
      const end = Date.now() + COUNTDOWN_S * 1000;
      while (Date.now() < end) {
        seconds.textContent = String(Math.ceil((end - Date.now()) / 1000));
        await sleep(100); // computed from the clock: a background tab runs timers once a second
      }
      countdown.hidden = true;
      go.disabled = false;
      if (document.hasFocus()) {
        alert.show(new ApiError("Not scanned: this page still had the focus, so the barcode would have been typed here.", "Press Scan again and click your POS window during the countdown."));
        return;
      }
    }
    await act(go, alert, () => call("POST", `${devicePath(device.id)}/scans`, { data: data.value, countdown_seconds: 0, unicode: exact.checked }));
  });
  const parts = [form];
  if (keyboard) parts.push(el("label", { class: "check" }, exact, "Type exact characters"));
  parts.push(countdown);
  return parts;
}

// --- the page -----------------------------------------------------------------------------

const builders = { printer: printerCard, scale: scaleCard, scanner: scannerCard };
const grid = document.getElementById("devices");
const eventRows = document.getElementById("events");
const filters = document.getElementById("filters");
const connection = document.getElementById("connection");
const pageAlert = alertBox();
document.getElementById("page-alert").replaceWith(pageAlert.node);
document.getElementById("address").textContent = location.host;

const views = new Map();
let shownIds = "";
let filter = "all";

async function loadDevices() {
  const devices = await call("GET", "/devices");
  const ids = devices.map((d) => d.id).join("\n");
  if (ids !== shownIds) {
    shownIds = ids;
    views.clear();
    const groups = new Map(Object.keys(builders).map((type) => [type, el("div", { class: "group" })]));
    for (const device of devices) {
      const view = builders[device.type](device);
      views.set(device.id, view);
      groups.get(device.type).append(view.node);
    }
    grid.replaceChildren(...[...groups.values()].filter((group) => group.childElementCount));
    buildFilters(devices.map((d) => d.id));
  }
  for (const device of devices) views.get(device.id).update(device.state);
  await Promise.all([...views.values()].map((view) => view.load?.()));
}

// One request in flight per device and at most one queued behind it (design D5).
const refreshing = new Map();
async function refresh(id) {
  if (refreshing.has(id)) {
    refreshing.set(id, true);
    return;
  }
  refreshing.set(id, false);
  try {
    views.get(id)?.update((await call("GET", devicePath(id))).state);
  } catch {
    // the next event or reconnect refreshes it
  }
  const again = refreshing.get(id);
  refreshing.delete(id);
  if (again) await refresh(id);
}

function buildFilters(ids) {
  filter = "all";
  filters.replaceChildren();
  for (const id of ["all", ...ids]) {
    const chip = el("button", { type: "button", class: "chip", "aria-pressed": String(id === "all") }, id === "all" ? "All devices" : id);
    chip.addEventListener("click", () => {
      filter = id;
      for (const other of filters.children) other.setAttribute("aria-pressed", String(other === chip));
      for (const row of eventRows.children) if (row.dataset.device) row.hidden = filter !== "all" && row.dataset.device !== filter;
    });
    filters.append(chip);
  }
}

function addEvent(event) {
  if (eventRows.querySelector(".empty")) eventRows.replaceChildren();
  const row = el(
    "tr",
    { class: "new", "data-device": event.device_id },
    el("td", { class: "t" }, clock(event.at)),
    el("td", {}, event.device_id),
    el("td", { class: "ty" }, event.type),
    el("td", { class: "data", dir: "auto" }, pairs(event.data)),
  );
  row.hidden = filter !== "all" && filter !== event.device_id;
  eventRows.prepend(row);
  while (eventRows.children.length > EVENT_LIMIT) eventRows.lastElementChild.remove();
}

function onEvent(event) {
  addEvent(event);
  const view = views.get(event.device_id);
  if (!view) return;
  view.onEvent?.(event);
  refresh(event.device_id);
}

function showConnection(kind, text) {
  connection.className = `pill ${kind}`;
  connection.textContent = text;
}

// Why the event stream closed: emupos stopped, or this address is refused (design D2).
async function diagnose() {
  try {
    await call("GET", "/health");
  } catch {
    showConnection("bad", "Not connected");
    pageAlert.show(new ApiError("emupos is not running.", "Start it with `emupos run --ui`; this page reconnects by itself."));
    return;
  }
  showConnection("bad", "Read-only");
  pageAlert.show(new ApiError("This address can show the devices but cannot act on them.", LOOPBACK_FIX));
  await loadDevices().catch(() => {});
}

// Subscribe first, then load: events are not replayed, so loading first could miss a change.
function connect() {
  const socket = new WebSocket(`ws://${location.host}${API}/events`);
  let opened = false;
  socket.addEventListener("open", () => {
    opened = true;
    showConnection("ok", "Connected");
    pageAlert.clear();
    loadDevices().catch((error) => pageAlert.show(error));
  });
  socket.addEventListener("message", (message) => onEvent(JSON.parse(message.data)));
  socket.addEventListener("close", () => {
    if (opened) showConnection("bad", "Not connected · retrying");
    else diagnose();
    setTimeout(connect, RETRY_MS);
  });
}

connect();
