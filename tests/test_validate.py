import json

import pytest

from aether.analysis import validate


SPEC = {
    "_meta": {"id": "SPEC-TEST"},
    "requirements": [
        {"id": "REQ-01", "signal": "i_dc", "applies_to": ["A", "B"],
         "tolerance": {"type": "relative", "value": 0.10},
         "falsifies": ["R_phase", "inverter loss model"]},
        {"id": "REQ-04", "signal": "temp_c", "applies_to": ["A", "B"],
         "tolerance": {"type": "absolute", "value": 5.0},
         "falsifies": ["r_thermal"]},
        {"id": "REQ-03", "signal": "u_bus", "applies_to": ["B"],
         "tolerance": {"type": "relative", "value": 0.02},
         "falsifies": ["r_internal"]},
    ],
}

PREDICTIONS = [
    {"id": "P1", "i_dc": 10.0, "temp_c": 30.0, "u_bus": 14.8},
    {"id": "P2", "i_dc": 20.0, "temp_c": 40.0, "u_bus": 14.4},
    {"id": "P3", "i_dc": 30.0, "temp_c": 50.0, "u_bus": 14.0},
]
PARAMS = {"k_e": 0.0106, "R_phase": 0.060}


def frozen(tmp_path, name="pred.json"):
    return validate.freeze(PREDICTIONS, SPEC, PARAMS, tmp_path / name)


# ----------------------------------------------------------------- tolerance
def test_relative_tolerance_is_taken_against_the_prediction():
    req = SPEC["requirements"][0]
    assert validate.tolerance_of(req, 20.0) == pytest.approx(2.0)
    assert validate.tolerance_of(req, -20.0) == pytest.approx(2.0)


def test_absolute_tolerance_ignores_magnitude():
    req = SPEC["requirements"][1]
    assert validate.tolerance_of(req, 30.0) == 5.0
    assert validate.tolerance_of(req, 300.0) == 5.0


def test_only_requirements_for_this_config_apply():
    assert len(validate.requirements_for(SPEC, "A")) == 2
    assert len(validate.requirements_for(SPEC, "B")) == 3


# -------------------------------------------------------------------- freeze
def test_freeze_records_time_and_fingerprint(tmp_path):
    payload = frozen(tmp_path)

    assert payload["spec_id"] == "SPEC-TEST"
    assert payload["frozen_at"].endswith("+00:00")
    assert len(payload["model_fingerprint"]) == 12
    assert json.loads((tmp_path / "pred.json").read_text())["predictions"] == PREDICTIONS


def test_freeze_refuses_to_overwrite(tmp_path):
    """The discipline, enforced. Re-freezing after a bench run hides tuning."""
    frozen(tmp_path)

    with pytest.raises(FileExistsError):
        frozen(tmp_path)

    # force is the deliberate escape hatch, and it must work
    validate.freeze(PREDICTIONS, SPEC, PARAMS, tmp_path / "pred.json", force=True)


def test_fingerprint_changes_when_a_parameter_changes():
    a = validate.fingerprint({"k_e": 0.0106})
    b = validate.fingerprint({"k_e": 0.0110})
    assert a != b
    assert a == validate.fingerprint({"k_e": 0.0106})


def test_compare_refuses_if_the_model_changed_since_the_freeze(tmp_path):
    f = frozen(tmp_path)
    tuned = dict(PARAMS, R_phase=0.055)      # someone "fixed" the model afterwards

    with pytest.raises(ValueError, match="model changed"):
        validate.compare(f, [], SPEC, "A", parameters=tuned)


# ------------------------------------------------------------------- compare
def test_a_perfect_measurement_passes_everything(tmp_path):
    f = frozen(tmp_path)
    rows = validate.compare(f, [dict(p) for p in PREDICTIONS], SPEC, "A")

    assert len(rows) == 6                      # 3 points x 2 requirements in config A
    assert all(r["verdict"] == "PASS" for r in rows)
    assert validate.summary(rows)["verdict"] == "PASS"


def test_an_error_just_inside_and_just_outside_the_gate(tmp_path):
    f = frozen(tmp_path)
    measured = [dict(p) for p in PREDICTIONS]
    measured[1]["i_dc"] = 20.0 * 1.099         # inside 10 %
    measured[2]["i_dc"] = 30.0 * 1.101         # outside

    rows = validate.compare(f, measured, SPEC, "A")
    verdicts = {(r["point"], r["signal"]): r["verdict"] for r in rows}

    assert verdicts[("P2", "i_dc")] == "PASS"
    assert verdicts[("P3", "i_dc")] == "FAIL"


def test_missing_points_and_signals_are_reported_not_skipped(tmp_path):
    f = frozen(tmp_path)
    measured = [PREDICTIONS[0], {"id": "P2", "temp_c": 40.0}]   # P3 absent, P2 partial

    rows = validate.compare(f, measured, SPEC, "A")
    verdicts = {(r["point"], r["signal"]): r["verdict"] for r in rows}

    assert verdicts[("P2", "i_dc")] == "MISSING_SIGNAL"
    assert verdicts[("P3", "i_dc")] == "MISSING_POINT"
    s = validate.summary(rows)
    assert s["n_missing"] == 3
    assert s["verdict"] == "FAIL"              # missing data is not a pass


# ------------------------------------------------------------------- summary
def test_systematic_bias_is_separated_from_scatter(tmp_path):
    f = frozen(tmp_path)

    # every point 8 % high, same direction: a wrong parameter
    biased = [dict(p, i_dc=p["i_dc"] * 1.08) for p in PREDICTIONS]
    s = validate.summary(validate.compare(f, biased, SPEC, "A"))
    assert s["by_signal"]["i_dc"]["systematic"] is True
    assert s["by_signal"]["i_dc"]["mean_error"] > 0

    # scattered both ways, mean near zero: measurement noise
    noisy = [dict(p, i_dc=p["i_dc"] + d) for p, d in zip(PREDICTIONS, (+0.6, -0.6, +0.5))]
    s = validate.summary(validate.compare(f, noisy, SPEC, "A"))
    assert s["by_signal"]["i_dc"]["systematic"] is False


def test_report_names_the_suspects_for_a_systematic_signal(tmp_path):
    f = frozen(tmp_path)
    biased = [dict(p, i_dc=p["i_dc"] * 1.20) for p in PREDICTIONS]
    rows = validate.compare(f, biased, SPEC, "A")

    text = validate.format_report(rows, validate.summary(rows), SPEC, "A")

    assert "SYSTEMATIC BIAS" in text
    assert "R_phase" in text                   # pulled from the spec's falsifies list
    assert "FAIL" in text


def test_the_real_spec_file_loads_and_is_self_consistent():
    spec = validate.load_spec(validate.SPEC_DIR / "spec_1.json")

    assert spec["_meta"]["id"] == "SPEC-1"
    for req in spec["requirements"]:
        assert req["tolerance"]["type"] in ("relative", "absolute")
        assert req["applies_to"]
        assert req["justification"]
    configs = set(spec["setup"]["configurations"])
    for req in spec["requirements"]:
        assert set(req["applies_to"]) <= configs
