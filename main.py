"""Thin launcher that re-exports split modules and delegates startup to app_entry.main()."""

from __future__ import annotations

from app_entry import main
import automation_engine as _automation_engine
import led_controller as _led_controller
import prayer_handler as _prayer_handler
import scene_manager as _scene_manager
import voice_handler as _voice_handler
def _export_module_symbols(module):
    for name, value in module.__dict__.items():
        if name.startswith("__"):
            continue
        globals().setdefault(name, value)


for _module in (
    _automation_engine,
    _led_controller,
    _prayer_handler,
    _scene_manager,
    _voice_handler,
):
    _export_module_symbols(_module)
if __name__ == "__main__":
    main()
