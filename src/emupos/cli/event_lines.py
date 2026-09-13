"""One readable line per simulator event, as shown live by `emupos run`."""

from collections import Counter
from collections.abc import Mapping
from typing import cast

from rich.text import Text

from emupos.cli.output import kilograms
from emupos.events import EventType, PublishedEvent

TYPE_WIDTH = max(len(kind) for kind in EventType)
FAMILY_STYLES = {
    "connection": "blue",
    "printer": "magenta",
    "drawer": "bright_magenta",
    "scale": "green",
    "scanner": "cyan",
    "snmp": "bright_blue",
}


class EventLines:
    def __init__(self, device_ids: list[str]) -> None:
        self._id_width = max((len(device_id) for device_id in device_ids), default=0)
        self._jobs = Counter[str]()  # completed jobs per printer since `emupos run` started

    def line(self, published: PublishedEvent) -> Text:
        event = published.event
        time = published.at.astimezone().strftime("%H:%M:%S.%f")[:-3]
        return Text.assemble(
            (time, "dim"),
            "  ",
            (event.device_id.ljust(self._id_width), "bold"),
            "  ",
            (event.type.ljust(TYPE_WIDTH), FAMILY_STYLES.get(event.type.split(".")[0], "")),
            "  ",
            self.summary(event.type, event.device_id, event.data),
        )

    def summary(self, kind: EventType, device_id: str, data: Mapping[str, object]) -> str:
        match kind:
            case EventType.CONNECTION_OPENED | EventType.CONNECTION_CLOSED:
                verb = "opened" if kind == EventType.CONNECTION_OPENED else "closed"
                client = f" from {data['client']}" if "client" in data else ""
                return f"{data.get('kind')} {data.get('endpoint')} {verb}{client}"
            case EventType.CONNECTION_FRAMING_MISMATCH:
                return f"framing mismatch on {data.get('endpoint')}"
            case EventType.PRINTER_JOB_COMPLETED:
                self._jobs[device_id] += 1
                job = self._jobs[device_id]
                return f"job {job} · {data.get('boundary')} → {data.get('receipt_id')}"
            case EventType.PRINTER_COMMAND_UNKNOWN:
                return f"skipped unknown bytes {data.get('bytes')}"
            case EventType.PRINTER_CODEPAGE_UNSUPPORTED:
                name = f" ({data['code_page']})" if "code_page" in data else ""
                return f"code page {data.get('number')}{name} is not supported"
            case EventType.PRINTER_STATUS_CHANGED:
                faults = cast(list[object], data.get("faults") or [])
                return f"faults: {', '.join(map(str, faults))}" if faults else "no faults"
            case EventType.DRAWER_OPENED:
                return f"drawer opened (pin {data.get('pin')})"
            case EventType.DRAWER_CLOSED:
                return "drawer closed"
            case EventType.SCALE_WEIGHT_CHANGED:
                return _weight(data)
            case EventType.SCALE_REQUEST_ANSWERED:
                return f"{data.get('request')} → {data.get('reply')}"
            case EventType.SCANNER_SCAN_DELIVERED:
                return f"scan delivered {data.get('data')}"
            case _:
                return " ".join(f"{key}={value}" for key, value in data.items())


def _weight(data: Mapping[str, object]) -> str:
    grams, tare, net = data.get("grams"), data.get("tare_grams"), data.get("net_grams")
    if not isinstance(grams, int) or not isinstance(tare, int) or not isinstance(net, int):
        return str(dict(data))
    text = f"{kilograms(grams)} {'stable' if data.get('stable') else 'in motion'}"
    return text + (f" (tare {kilograms(tare)}, net {kilograms(net)})" if tare else "")
