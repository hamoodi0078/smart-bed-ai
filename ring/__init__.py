"""Smart Ring BLE integration for Danah Smart Bed AI.

Provides BLE communication with COLMI R02/R06/R10 open-source smart rings,
sensor fusion with existing bed hardware, and ring-enhanced sleep intelligence.

Feature-gated: set RING_ENABLED=1 in .env to activate.
When disabled, all public APIs return noop/empty results safely.
"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ring.ble_client import NoopRingClient, RingBleClient
    from ring.automation import RingAutomationEngine

__all__ = [
    "RingBleClient",
    "NoopRingClient",
    "RingAutomationEngine",
    "build_ring_client",
]


def build_ring_client(settings: object) -> "RingBleClient | NoopRingClient":
    """Factory: create a ring client from app settings.

    Returns a real *RingBleClient* when the ring feature is enabled and
    the ``bleak`` library is installed, otherwise returns a *NoopRingClient*.
    """
    enabled = bool(getattr(settings, "ring_enabled", False))
    if not enabled:
        from ring.ble_client import NoopRingClient
        return NoopRingClient(reason="Ring disabled by configuration (RING_ENABLED=0).")

    try:
        from ring.ble_client import RingBleClient  # noqa: F811
        return RingBleClient(
            ble_address=str(getattr(settings, "ring_ble_address", "") or ""),
            model=str(getattr(settings, "ring_model", "colmi_r02") or "colmi_r02"),
            auto_connect=bool(getattr(settings, "ring_auto_connect", True)),
            realtime_hr=bool(getattr(settings, "ring_realtime_hr_enabled", True)),
            realtime_spo2=bool(getattr(settings, "ring_realtime_spo2_enabled", True)),
            sync_interval_minutes=int(getattr(settings, "ring_sync_interval_minutes", 30)),
        )
    except ImportError:
        from ring.ble_client import NoopRingClient
        return NoopRingClient(reason="Ring disabled: install bleak (pip install bleak>=0.21.0).")
    except Exception as exc:
        from ring.ble_client import NoopRingClient
        return NoopRingClient(reason=f"Ring init failed: {exc}")
