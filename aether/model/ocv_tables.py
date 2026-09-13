"""Open-circuit-voltage tables, loaded from data/ocv_tables.json.

The data lives in JSON so it can be edited, diffed and replaced without
touching code. When you measure your own cells, write a new JSON with the same
shape and point DATA_FILE at it.

Read the "_provenance" block in that file before trusting any number. The
shipped tables are nominal shapes carried over from GAIA, not measurements.
"""

import json
from pathlib import Path

from aether.model.cell import Cell_advanced

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "ocv_tables.json"


def _load(path=None):
    raw = json.loads(Path(path or DATA_FILE).read_text(encoding="utf-8"))
    soc = raw["soc_points"]
    for name, entry in raw["chemistries"].items():
        if len(entry["ocv"]) != len(soc):
            raise ValueError(f"{name}: {len(entry['ocv'])} ocv points for "
                             f"{len(soc)} soc points")
    return raw


_DATA = _load()
SOC_POINTS = _DATA["soc_points"]
TABLES = _DATA["chemistries"]
PROVENANCE = _DATA["_provenance"]


def available():
    """Chemistry names you can pass to make_cell()."""
    return sorted(TABLES)


def table(chemistry):
    """(soc_points, ocv_points) for one chemistry."""
    key = chemistry.upper()
    if key not in TABLES:
        raise KeyError(f"no table for {chemistry!r}. have: {', '.join(available())}")
    return list(SOC_POINTS), list(TABLES[key]["ocv"])


def describe(chemistry):
    entry = TABLES[chemistry.upper()]
    return (f"{chemistry.upper()}: {entry['ocv'][0]:.2f} V empty, "
            f"{entry['ocv'][-1]:.2f} V full. {entry['note']} "
            f"[{entry['source']}]")


def make_cell(chemistry, capacity_ah, r_internal, i_max, **kwargs):
    """Build a Cell_advanced with this chemistry's OCV table.

    Capacity, resistance and current limit stay yours to supply: those are
    specimen properties, not chemistry properties.
    """
    soc_points, ocv_points = table(chemistry)
    return Cell_advanced(chemistry=chemistry.upper(), capacity_ah=capacity_ah,
                         r_internal=r_internal, soc_points=soc_points,
                         ocv_points=ocv_points, i_max=i_max, **kwargs)


if __name__ == "__main__":
    print(f"{DATA_FILE.name}: {PROVENANCE['status']}\n")
    for name in available():
        print(describe(name))
        print()
