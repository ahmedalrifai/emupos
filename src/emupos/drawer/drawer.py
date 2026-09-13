"""The cash drawer attached to a printer's drawer kick-out connector (cash-drawer spec).

The drawer opens on a pulse (ESC p, or DLE DC4 fn 1) and stays open until the operator
closes it; it never closes by itself. Its sensor is read on connector pin 3.
- ESC p: https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/esc_lp.html
- DLE DC4 fn 1: https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/dle_dc4_fn1.html
"""

from dataclasses import dataclass

from emupos.config import Level
from emupos.events import Event, EventType


@dataclass(frozen=True, slots=True)
class Pulse:
    pin: int  # drawer kick-out connector pin: 2 or 5
    on_time_ms: int


def esc_p_pulse(m: int, t1: int) -> Pulse | None:
    """ESC p m t1 t2: m = 0/48 is pin 2, 1/49 is pin 5; the ON time is t1 x 2 ms."""
    pins = {0: 2, 48: 2, 1: 5, 49: 5}
    return Pulse(pins[m], t1 * 2) if m in pins else None


def dle_dc4_pulse(m: int, t: int) -> Pulse | None:
    """DLE DC4 1 m t: m = 0 is pin 2, 1 is pin 5; t = 1-8 gives an ON time of t x 100 ms."""
    if m not in (0, 1) or not 1 <= t <= 8:
        return None
    return Pulse(2 if m == 0 else 5, t * 100)


class Drawer:
    def __init__(self, device_id: str, sensor_open_level: Level) -> None:
        self._device_id = device_id
        self._sensor_open_level = sensor_open_level
        self.is_open = False  # closed when the simulator starts

    @property
    def pin3_high(self) -> bool:
        """Connector pin 3 is at the configured level while open, the opposite while closed."""
        return self.is_open == (self._sensor_open_level == "high")

    def kick(self, pulse: Pulse) -> Event | None:
        """Open the drawer; `drawer.opened` only when it was closed."""
        if self.is_open:
            return None
        self.is_open = True
        return Event(
            EventType.DRAWER_OPENED,
            self._device_id,
            {"pin": pulse.pin, "on_time_ms": pulse.on_time_ms},
        )

    def close(self) -> Event | None:
        """Close the drawer; `drawer.closed` only when it was open."""
        if not self.is_open:
            return None
        self.is_open = False
        return Event(EventType.DRAWER_CLOSED, self._device_id)
