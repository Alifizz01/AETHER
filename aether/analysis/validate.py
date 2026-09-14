"""Compare a frozen model prediction against measured bench data.

The order matters more than the code:

    1. run the model over the scenario          -> predictions
    2. freeze(), which refuses to overwrite     -> predicted_*.json
    3. go to the bench, measure
    4. compare()                                -> PASS / FAIL per signal per point
    5. summary(), which separates BIAS from SCATTER

Step 2 is the whole point. Once predictions are on disk with a timestamp and a
fingerprint of the model parameters, tuning a coefficient afterwards to make
the numbers agree is visible instead of invisible.

A failing requirement is not yet a defect. It becomes one when you can name the
parameter that caused it. That is what summary() is for:

    systematic bias  ->  a parameter in the model is wrong
    scatter          ->  the measurement is noisy, or the rig is not settling
"""

import hashlib
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

SPEC_DIR = Path(__file__).resolve().parents[1] / "scenario"


# --------------------------------------------------------------------- spec
def load_spec(path):
    """Read a spec JSON (see aether/scenario/spec_1.json for the shape)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def requirements_for(spec, config):
    """Only the requirements that apply to this configuration."""
    return [r for r in spec["requirements"] if config in r["applies_to"]]


def tolerance_of(requirement, predicted):
    """Absolute tolerance in the signal's own units.

    Relative tolerances are taken against the PREDICTED value, not the measured
    one. Using the measurement would let a bad measurement widen its own gate.
    """
    tol = requirement["tolerance"]
    if tol["type"] == "absolute":
        return abs(tol["value"])
    return abs(predicted) * tol["value"]


# ------------------------------------------------------------------- freeze
def fingerprint(parameters):
    """Short hash of the model parameters used to make the predictions.

    If this differs at compare time, the model changed after the freeze and the
    comparison is not a test any more.
    """
    blob = json.dumps(parameters, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def freeze(predictions, spec, parameters, path, force=False):
    """Write predictions to disk BEFORE measuring. Refuses to overwrite.

    The refusal is deliberate. Re-freezing after seeing data is exactly the
    mistake this file exists to prevent.
    """
    path = Path(path)
    if path.exists() and not force:
        raise FileExistsError(
            f"{path.name} already exists. Re-freezing after a measurement turns a "
            f"test into a curve fit. Pass force=True only if no bench run has "
            f"happened against it yet.")
    payload = {
        "spec_id": spec["_meta"]["id"],
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_fingerprint": fingerprint(parameters),
        "parameters": parameters,
        "predictions": predictions,
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return payload


def load_frozen(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ compare
def compare(frozen, measured, spec, config, parameters=None):
    """One row per (point, requirement). Missing data is reported, not skipped.

    measured: list of dicts, each with an "id" matching a scenario point.
    """
    if parameters is not None:
        now = fingerprint(parameters)
        if now != frozen["model_fingerprint"]:
            raise ValueError(
                f"model changed since freeze ({frozen['model_fingerprint']} -> {now}). "
                f"The comparison would not be a test. Re-run the prediction, or "
                f"compare against the model as it was.")

    by_id = {m["id"]: m for m in measured}
    reqs = requirements_for(spec, config)
    rows = []

    for pred in frozen["predictions"]:
        pid = pred["id"]
        meas = by_id.get(pid)
        for req in reqs:
            sig = req["signal"]
            row = {"point": pid, "config": config, "req": req["id"], "signal": sig,
                   "predicted": pred.get(sig), "measured": None, "error": None,
                   "error_rel": None, "tolerance": None, "verdict": None}

            if meas is None:
                row["verdict"] = "MISSING_POINT"
            elif sig not in meas:
                row["verdict"] = "MISSING_SIGNAL"
            elif pred.get(sig) is None:
                row["verdict"] = "NOT_PREDICTED"
            else:
                p, m = pred[sig], meas[sig]
                tol = tolerance_of(req, p)
                row.update(measured=m, error=m - p, tolerance=tol,
                           error_rel=(m - p) / p if p else None,
                           verdict="PASS" if abs(m - p) <= tol else "FAIL")
            rows.append(row)
    return rows


# ------------------------------------------------------------------ summary
def summary(rows, bias_ratio=1.0):
    """Counts, worst case per signal, and bias vs scatter.

    A signal is called systematic when the mean error is larger than the spread
    of the errors: every point is wrong in the same direction by a similar
    amount, which is what a wrong parameter looks like. Scatter with a mean near
    zero is measurement noise, not a model defect.
    """
    out = {"n_rows": len(rows),
           "n_pass": sum(r["verdict"] == "PASS" for r in rows),
           "n_fail": sum(r["verdict"] == "FAIL" for r in rows),
           "n_missing": sum(str(r["verdict"]).startswith(("MISSING", "NOT_")) for r in rows),
           "by_signal": {}}

    for sig in sorted({r["signal"] for r in rows}):
        errs = [r["error"] for r in rows if r["signal"] == sig and r["error"] is not None]
        if not errs:
            continue
        mean = statistics.fmean(errs)
        spread = statistics.pstdev(errs) if len(errs) > 1 else 0.0
        worst = max(rows_for := [r for r in rows if r["signal"] == sig
                                 and r["error"] is not None],
                    key=lambda r: abs(r["error"]))
        out["by_signal"][sig] = {
            "n": len(errs),
            "mean_error": mean,
            "spread": spread,
            "worst_error": worst["error"],
            "worst_point": worst["point"],
            "systematic": abs(mean) > bias_ratio * spread,
            "n_fail": sum(r["verdict"] == "FAIL" for r in rows_for),
        }
    out["verdict"] = "PASS" if out["n_fail"] == 0 and out["n_missing"] == 0 else "FAIL"
    return out


def format_report(rows, summ, spec, config):
    """Plain text, because a report you can paste into a commit message gets read."""
    lines = [f"{spec['_meta']['id']}  config {config}  ->  {summ['verdict']}",
             f"{summ['n_pass']} pass, {summ['n_fail']} fail, "
             f"{summ['n_missing']} missing, of {summ['n_rows']} checks", ""]

    lines.append(f"{'point':>6} {'req':>7} {'signal':>8} {'predicted':>11} "
                 f"{'measured':>11} {'error':>10} {'tol':>9}  verdict")
    for r in rows:
        p = f"{r['predicted']:11.4g}" if r["predicted"] is not None else f"{'-':>11}"
        m = f"{r['measured']:11.4g}" if r["measured"] is not None else f"{'-':>11}"
        e = f"{r['error']:10.4g}" if r["error"] is not None else f"{'-':>10}"
        t = f"{r['tolerance']:9.4g}" if r["tolerance"] is not None else f"{'-':>9}"
        lines.append(f"{r['point']:>6} {r['req']:>7} {r['signal']:>8} {p} {m} {e} {t}  "
                     f"{r['verdict']}")

    lines += ["", "per signal:"]
    for sig, s in summ["by_signal"].items():
        kind = "SYSTEMATIC BIAS" if s["systematic"] else "scatter"
        lines.append(f"  {sig:>8}  mean {s['mean_error']:+.4g}  spread {s['spread']:.4g}  "
                     f"worst {s['worst_error']:+.4g} at {s['worst_point']}  "
                     f"{s['n_fail']} fail  -> {kind}")
        if s["systematic"]:
            req = next((r for r in spec["requirements"] if r["signal"] == sig), None)
            if req and req.get("falsifies"):
                lines.append(f"            same direction every point. suspects: "
                             f"{', '.join(req['falsifies'])}")
    return "\n".join(lines)
