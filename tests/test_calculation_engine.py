"""Unit tests for the Net Metering calculation engine.

All energy values are in kWh.
"""

import importlib
import sys
from pathlib import Path

import pytest

# Import the engine module directly so we don't pull in HA dependencies
# via the package __init__.
_engine_path = (
    Path(__file__).parent.parent
    / "custom_components"
    / "net_metering"
    / "calculation_engine.py"
)

# The engine does `from .const import PRECISION` (relative import).
# We register a stub under the package path it expects.
_const = type(sys)("net_metering.const")
_const.PRECISION = 6
sys.modules["net_metering.const"] = _const
sys.modules["custom_components.net_metering.const"] = _const

_spec = importlib.util.spec_from_file_location(
    "custom_components.net_metering.calculation_engine",
    _engine_path,
    submodule_search_locations=[],
)
_engine = importlib.util.module_from_spec(_spec)
_engine.__package__ = "custom_components.net_metering"
sys.modules["custom_components.net_metering.calculation_engine"] = _engine
_spec.loader.exec_module(_engine)
run_calculation = _engine.run_calculation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(
    *,
    current_solar=None,
    current_energy,
    previous_solar=None,
    previous_energy=None,
    solar_ref_valid=True,
    cumulative_import=0.0,
    cumulative_export=0.0,
    is_reference_cycle=False,
):
    return run_calculation(
        current_solar=current_solar,
        current_energy=current_energy,
        previous_solar=previous_solar,
        previous_energy=previous_energy,
        solar_ref_valid=solar_ref_valid,
        cumulative_import=cumulative_import,
        cumulative_export=cumulative_export,
        is_reference_cycle=is_reference_cycle,
    )


# ---------------------------------------------------------------------------
# Reference cycle
# ---------------------------------------------------------------------------


class TestReferenceCycle:
    def test_reference_cycle_produces_zero_deltas(self):
        r = _run(
            current_solar=5.0,
            current_energy=10.0,
            previous_solar=4.0,
            previous_energy=9.0,
            is_reference_cycle=True,
            cumulative_import=100.0,
            cumulative_export=50.0,
        )
        assert r.reference_only is True
        assert r.interval_import == 0.0
        assert r.interval_export == 0.0
        # Cumulative totals must not change
        assert r.cumulative_import == 100.0
        assert r.cumulative_export == 50.0

    def test_first_run_no_previous_energy_is_reference(self):
        r = _run(
            current_solar=3.0,
            current_energy=15.0,
            previous_energy=None,
            cumulative_import=0.0,
            cumulative_export=0.0,
        )
        assert r.reference_only is True
        assert r.cumulative_import == 0.0
        assert r.cumulative_export == 0.0


# ---------------------------------------------------------------------------
# Normal export
# ---------------------------------------------------------------------------


class TestExport:
    def test_solar_exceeds_consumption(self):
        # solar_delta=0.450, energy_delta=0.200, net=+0.250 → export
        r = _run(
            current_solar=13.490,
            current_energy=20.098,
            previous_solar=13.040,
            previous_energy=19.898,
        )
        assert r.reference_only is False
        assert r.rollback_detected is False
        assert r.interval_export == pytest.approx(0.250, abs=1e-6)
        assert r.interval_import == 0.0
        assert r.cumulative_export == pytest.approx(0.250, abs=1e-6)
        assert r.cumulative_import == 0.0

    def test_export_accumulates(self):
        r = _run(
            current_solar=14.000,
            current_energy=20.200,
            previous_solar=13.490,
            previous_energy=20.098,
            cumulative_import=0.0,
            cumulative_export=0.250,
        )
        assert r.interval_export == pytest.approx(0.408, abs=1e-6)
        assert r.cumulative_export == pytest.approx(0.658, abs=1e-6)


# ---------------------------------------------------------------------------
# Normal import
# ---------------------------------------------------------------------------


class TestImport:
    def test_consumption_exceeds_solar(self):
        # solar_delta=0.100, energy_delta=0.418107, net=-0.318107 → import
        r = _run(
            current_solar=5.100,
            current_energy=20.098260,
            previous_solar=5.000,
            previous_energy=19.680153,
        )
        assert r.interval_import == pytest.approx(0.318107, abs=1e-6)
        assert r.interval_export == 0.0
        assert r.cumulative_import == pytest.approx(0.318107, abs=1e-6)

    def test_zero_solar_all_import(self):
        r = _run(
            current_solar=0.0,
            current_energy=20.500,
            previous_solar=0.0,
            previous_energy=20.000,
        )
        assert r.interval_import == pytest.approx(0.500, abs=1e-6)
        assert r.interval_export == 0.0

    def test_import_accumulates(self):
        r = _run(
            current_solar=5.100,
            current_energy=20.500,
            previous_solar=5.000,
            previous_energy=20.000,
            cumulative_import=1.000,
            cumulative_export=0.0,
        )
        assert r.interval_import == pytest.approx(0.400, abs=1e-6)
        assert r.cumulative_import == pytest.approx(1.400, abs=1e-6)


# ---------------------------------------------------------------------------
# Equal – neither import nor export
# ---------------------------------------------------------------------------


class TestZeroNet:
    def test_equal_deltas_produces_zero(self):
        r = _run(
            current_solar=10.500,
            current_energy=20.500,
            previous_solar=10.000,
            previous_energy=20.000,
        )
        assert r.net == 0.0
        assert r.interval_import == 0.0
        assert r.interval_export == 0.0


# ---------------------------------------------------------------------------
# Solar unavailable
# ---------------------------------------------------------------------------


class TestSolarUnavailable:
    def test_solar_none_gives_zero_delta_solar(self):
        r = _run(
            current_solar=None,
            current_energy=20.500,
            previous_solar=13.040,
            previous_energy=20.000,
        )
        assert r.solar_unavailable is True
        assert r.delta_solar == 0.0
        # All consumption treated as import (no solar contribution)
        assert r.interval_import == pytest.approx(0.500, abs=1e-6)
        assert r.interval_export == 0.0

    def test_solar_recovers_from_correct_reference(self):
        """After unavailable period the delta should be from the last valid ref."""
        # Previous valid solar was 13.040; solar was unavailable; now 13.490
        r = _run(
            current_solar=13.490,
            current_energy=20.300,
            previous_solar=13.040,   # preserved through unavailable period
            previous_energy=20.000,
        )
        assert r.delta_solar == pytest.approx(0.450, abs=1e-6)
        assert r.delta_energy == pytest.approx(0.300, abs=1e-6)
        assert r.net == pytest.approx(0.150, abs=1e-6)
        assert r.interval_export == pytest.approx(0.150, abs=1e-6)


# ---------------------------------------------------------------------------
# Rollback / counter reset
# ---------------------------------------------------------------------------


class TestRollback:
    def test_energy_rollback_produces_zero(self):
        r = _run(
            current_solar=10.0,
            current_energy=0.050,   # rolled back from 50.000
            previous_solar=10.0,
            previous_energy=50.000,
        )
        assert r.rollback_detected is True
        assert r.reference_only is True
        assert r.interval_import == 0.0
        assert r.interval_export == 0.0
        # Cumulative totals unchanged
        assert r.cumulative_import == 0.0
        assert r.cumulative_export == 0.0

    def test_solar_rollback_produces_zero(self):
        r = _run(
            current_solar=0.050,    # rolled back from 50.000
            current_energy=20.500,
            previous_solar=50.000,
            previous_energy=20.000,
        )
        assert r.rollback_detected is True
        assert r.reference_only is True
        assert r.interval_import == 0.0
        assert r.interval_export == 0.0

    def test_next_cycle_after_rollback(self):
        """After rollback the fresh reference produces correct delta."""
        # Simulates: rollback set previous_energy=0.050; now current=0.100
        r = _run(
            current_solar=5.0,
            current_energy=0.100,
            previous_solar=0.0,
            previous_energy=0.050,
        )
        assert r.rollback_detected is False
        assert r.delta_energy == pytest.approx(0.050, abs=1e-6)
        assert r.delta_solar == pytest.approx(5.0, abs=1e-6)
        assert r.interval_export == pytest.approx(4.950, abs=1e-6)


# ---------------------------------------------------------------------------
# Precision
# ---------------------------------------------------------------------------


class TestPrecision:
    def test_delta_rounded_to_6_places(self):
        r = _run(
            current_solar=0.0,
            current_energy=20.0981234567,
            previous_solar=0.0,
            previous_energy=19.6801234567,
        )
        # raw delta = 0.4180000000; rounded = 0.418000
        assert r.delta_energy == pytest.approx(0.418000, abs=1e-7)

    def test_cumulative_rounding(self):
        r = _run(
            current_solar=0.0,
            current_energy=20.098260,
            previous_solar=0.0,
            previous_energy=19.680153,
            cumulative_import=1.234567,
        )
        expected = round(1.234567 + 0.418107, 6)
        assert r.cumulative_import == pytest.approx(expected, abs=1e-9)

    def test_no_floating_point_bleed(self):
        """Running many cycles should not produce uncontrolled drift."""
        cum_import = 0.0
        cum_export = 0.0
        energy = 0.0
        solar = 0.0
        prev_energy = 0.0
        prev_solar = 0.0

        for i in range(1000):
            energy += 0.0041
            solar += 0.002

            r = run_calculation(
                current_solar=solar,
                current_energy=energy,
                previous_solar=prev_solar,
                previous_energy=prev_energy,
                solar_ref_valid=True,
                cumulative_import=cum_import,
                cumulative_export=cum_export,
                is_reference_cycle=False,
            )
            cum_import = r.cumulative_import
            cum_export = r.cumulative_export
            prev_energy = energy
            prev_solar = solar

        # Each cycle: delta_energy=0.0041, delta_solar=0.002, net=-0.0021
        # → import per cycle = 0.0021, over 1000 cycles = 2.1 kWh
        assert cum_import == pytest.approx(2.1, abs=0.01)
        assert cum_export == pytest.approx(0.0, abs=1e-4)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_both_sensors_at_zero_gives_zero(self):
        r = _run(
            current_solar=0.0,
            current_energy=0.0,
            previous_solar=0.0,
            previous_energy=0.0,
        )
        assert r.net == 0.0
        assert r.interval_import == 0.0
        assert r.interval_export == 0.0

    def test_solar_at_zero_all_import(self):
        r = _run(
            current_solar=0.0,
            current_energy=5.000,
            previous_solar=0.0,
            previous_energy=4.500,
        )
        assert r.interval_import == pytest.approx(0.500, abs=1e-6)

    def test_no_change_in_both_sensors(self):
        r = _run(
            current_solar=10.0,
            current_energy=20.0,
            previous_solar=10.0,
            previous_energy=20.0,
        )
        assert r.net == 0.0
        assert r.interval_import == 0.0
        assert r.interval_export == 0.0
