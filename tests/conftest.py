"""pytest configuration – adds the integration src to sys.path."""

import sys
import types
from pathlib import Path

# Allow direct imports of the integration modules.
sys.path.insert(0, str(Path(__file__).parent.parent))

# ---------------------------------------------------------------------------
# Minimal stubs so that non-engine modules (which import homeassistant.*)
# can be imported without a full HA installation.  The calculation_engine
# itself has no HA dependencies and needs no stubs.
# ---------------------------------------------------------------------------

def _make_stub(*names):
    """Return a module stub for the given dotted name."""
    parts = names[0].split(".")
    parent = None
    for i, part in enumerate(parts):
        full = ".".join(parts[: i + 1])
        if full not in sys.modules:
            mod = types.ModuleType(full)
            sys.modules[full] = mod
            if parent is not None:
                setattr(parent, part, mod)
        parent = sys.modules[full]
    return parent

for _stub in [
    "homeassistant",
    "homeassistant.core",
    "homeassistant.config_entries",
    "homeassistant.const",
    "homeassistant.components",
    "homeassistant.components.sensor",
    "homeassistant.components.binary_sensor",
    "homeassistant.helpers",
    "homeassistant.helpers.storage",
    "homeassistant.helpers.event",
    "homeassistant.helpers.update_coordinator",
    "homeassistant.helpers.entity",
    "homeassistant.helpers.entity_platform",
    "homeassistant.helpers.device_registry",
    "homeassistant.helpers.config_validation",
    "homeassistant.helpers.selector",
    "voluptuous",
]:
    _make_stub(_stub)
