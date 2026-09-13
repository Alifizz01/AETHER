import pytest

from aether.model.cell import Cell_advanced
from aether.model import ocv_tables


def test_every_table_is_usable_by_cell_advanced():
    """Cell_advanced validates its own table, so this proves all five are valid."""
    for name in ocv_tables.available():
        cell = ocv_tables.make_cell(name, capacity_ah=3.0, r_internal=0.020, i_max=30.0)
        assert isinstance(cell, Cell_advanced)
        assert cell.chemistry == name
        assert len(cell.soc_points) == len(cell.ocv_points) == 11


def test_tables_rise_monotonically_with_soc():
    """A cell that gains voltage as it empties would be a bug, not a chemistry."""
    for name in ocv_tables.available():
        _, ocv = ocv_tables.table(name)
        assert all(b > a for a, b in zip(ocv, ocv[1:])), name


def test_endpoints_match_the_quoted_gaia_numbers():
    assert ocv_tables.table("NMC")[1][0] == pytest.approx(2.50)
    assert ocv_tables.table("NMC")[1][-1] == pytest.approx(4.20)
    assert ocv_tables.table("LFP")[1][-1] == pytest.approx(3.45)
    assert ocv_tables.table("LTO")[1][-1] == pytest.approx(2.80)


def test_lfp_is_much_flatter_than_nmc_in_the_middle():
    """The reason chemistry choice changes how you estimate SOC."""
    def span(name, lo=0.4, hi=0.9):
        cell = ocv_tables.make_cell(name, 3.0, 0.020, 30.0)
        cell.soc = hi
        top = cell.u_ocv()
        cell.soc = lo
        return top - cell.u_ocv()

    assert span("LFP") < 0.30          # 3.10 -> 3.40 V across half the range
    assert span("NMC") > 0.45          # 3.65 -> 4.15 V
    assert span("LFP") < span("NMC") / 1.5


def test_lmo_is_a_known_duplicate_of_nmc():
    """Documented upstream defect. If this ever fails, GAIA fixed its table."""
    assert ocv_tables.table("LMO")[1] == ocv_tables.table("NMC")[1]


def test_unknown_chemistry_is_rejected():
    with pytest.raises(KeyError):
        ocv_tables.table("LiPo")       # deliberately absent, see the module docstring


def test_lookup_is_case_insensitive():
    assert ocv_tables.table("nmc") == ocv_tables.table("NMC")
