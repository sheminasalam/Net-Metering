"""
Net Metering – Calculation Engine.

Pure, stateless calculation logic translated from the Node-RED reference
implementation.  All energy values are in kWh, rounded to PRECISION decimal
places.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .const import PRECISION


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------


@dataclass
class CalculationResult:
    """Result produced by a single engine call."""

    # Inputs
    current_solar: Optional[float]       # None when unavailable
    current_energy: float

    # Deltas
    delta_solar: float = 0.0
    delta_energy: float = 0.0
    net: float = 0.0

    # Interval import / export
    interval_import: float = 0.0
    interval_export: float = 0.0

    # Updated cumulative totals
    cumulative_import: float = 0.0
    cumulative_export: float = 0.0

    # Flags
    reference_only: bool = False
    rollback_detected: bool = False
    solar_unavailable: bool = False

    # Diagnostics
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def run_calculation(
    *,
    current_solar: Optional[float],
    current_energy: float,
    previous_solar: Optional[float],
    previous_energy: Optional[float],
    solar_ref_valid: bool,
    cumulative_import: float,
    cumulative_export: float,
    is_reference_cycle: bool,
) -> CalculationResult:
    """
    Execute one calculation cycle.

    Parameters
    ----------
    current_solar:
        Current Solar Production reading (kWh), or None if unavailable.
    current_energy:
        Current Energy Consumption reading (kWh).  Caller guarantees this is
        a finite number (invalid energy is handled at the coordinator level).
    previous_solar:
        Previous valid Solar reference (kWh), or None if never set.
    previous_energy:
        Previous Energy Consumption reference (kWh), or None if never set.
    solar_ref_valid:
        True when previous_solar came from a real sensor reading (not the
        synthetic zero used when solar was unavailable at init time).
    cumulative_import:
        Current cumulative Grid Import total (kWh).
    cumulative_export:
        Current cumulative Grid Export total (kWh).
    is_reference_cycle:
        True when the caller has already determined this should be a
        reference-only cycle (first run, new date, missing references, …).

    Returns
    -------
    CalculationResult
        Contains updated cumulative totals and diagnostic data.  The caller
        is responsible for persisting state.
    """

    solar_unavailable = current_solar is None or not math.isfinite(current_solar)

    result = CalculationResult(
        current_solar=current_solar,
        current_energy=current_energy,
        solar_unavailable=solar_unavailable,
        cumulative_import=cumulative_import,
        cumulative_export=cumulative_export,
    )

    # ------------------------------------------------------------------
    # Reference-only cycle
    # ------------------------------------------------------------------

    if is_reference_cycle:
        result.reference_only = True
        result.notes.append("Reference established; no energy added.")
        return result

    # ------------------------------------------------------------------
    # Guard: previous references must exist for a normal cycle
    # ------------------------------------------------------------------

    if previous_energy is None or not math.isfinite(previous_energy):
        result.reference_only = True
        result.notes.append("No valid previous energy reference; treating as reference cycle.")
        return result

    # ------------------------------------------------------------------
    # Delta calculation
    # ------------------------------------------------------------------

    delta_energy = current_energy - previous_energy

    if solar_unavailable:
        # Solar unavailable → contribution is zero; preserve solar reference
        delta_solar = 0.0
        result.notes.append("Solar unavailable; delta_solar = 0.")
    else:
        if previous_solar is None or not math.isfinite(previous_solar):
            # Solar just became available but we had no reference yet
            delta_solar = 0.0
            result.notes.append("Solar reference not yet established; delta_solar = 0.")
        else:
            delta_solar = current_solar - previous_solar  # type: ignore[operator]

    # ------------------------------------------------------------------
    # Rollback / counter-reset detection
    # ------------------------------------------------------------------

    rollback = False

    if delta_energy < 0:
        rollback = True
        result.notes.append(
            f"Energy counter rollback detected "
            f"(delta_energy={delta_energy:.{PRECISION}f}); new reference set."
        )

    if not solar_unavailable and delta_solar < 0:
        rollback = True
        result.notes.append(
            f"Solar counter rollback detected "
            f"(delta_solar={delta_solar:.{PRECISION}f}); new reference set."
        )

    if rollback:
        result.rollback_detected = True
        result.reference_only = True
        # Cumulative totals unchanged; caller will update references
        return result

    # ------------------------------------------------------------------
    # Round deltas (matches Node-RED toFixed(6))
    # ------------------------------------------------------------------

    delta_energy = round(delta_energy, PRECISION)
    delta_solar = round(delta_solar, PRECISION)

    # ------------------------------------------------------------------
    # Net grid flow
    # ------------------------------------------------------------------

    net = round(delta_solar - delta_energy, PRECISION)

    delta_import = 0.0
    delta_export = 0.0

    if net > 0:
        delta_export = net
        cumulative_export = round(cumulative_export + delta_export, PRECISION)
    elif net < 0:
        delta_import = abs(net)
        cumulative_import = round(cumulative_import + delta_import, PRECISION)

    # ------------------------------------------------------------------
    # Populate result
    # ------------------------------------------------------------------

    result.delta_solar = delta_solar
    result.delta_energy = delta_energy
    result.net = net
    result.interval_import = delta_import
    result.interval_export = delta_export
    result.cumulative_import = cumulative_import
    result.cumulative_export = cumulative_export

    return result
