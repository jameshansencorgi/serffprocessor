"""Score an extraction run against tests/golden/extraction_eval.yml.

Usage:
  .venv/bin/python scripts/eval_extraction.py --regex
  .venv/bin/python scripts/eval_extraction.py --facts /path/to/run.json   [--label NAME]

`run.json` is either a list of {doc, facts:[{catalogue_key,value,...}]} or a workflow
result wrapped as {"result": [...]}. This is the test harness for the improve loop:
edit a model/prompt, produce a run.json, score it, compare the delta. Reports recall by
layout bucket, vocabulary accuracy, hallucination (value-in-source), and fact volume.
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
TEXTDIR = ROOT / "data/processed/text"
EVAL = yaml.safe_load((ROOT / "tests/golden/extraction_eval.yml").read_text())
ALIASES = EVAL.get("key_aliases", {})


def first_float(s):
    if s is None:
        return None
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(s).replace("$", ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def value_match(v, x):
    return abs(x - v) <= max(0.05, abs(v) * 0.001)


def load_run(path):
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict) and "result" in data:
        data = data["result"]
    return {r["doc"]: r["facts"] for r in data}


def regex_run():
    from serff_intel.extract.rate_impact import extract_rate_facts
    from serff_intel.extract.actuarial_reasons import extract_reason_facts
    from serff_intel.extract.objections import extract_objection_facts
    out = {}
    for doc in EVAL["docs"]:
        text = (TEXTDIR / f"{doc}.txt").read_text()
        facts = extract_rate_facts(text) + extract_reason_facts(text) + extract_objection_facts(text)
        out[doc] = [{"catalogue_key": f.fact_key or f.fact_type, "value": f.normalized_value} for f in facts]
    return out


def acceptable_key(expected, got):
    if got == expected:
        return True
    return got in ALIASES.get(expected, [expected])


def score(run, label):
    buckets = ["labeled_scalar", "labeled_series", "grid_cell"]
    tally = {b: {"n": 0, "hit": 0} for b in buckets}
    vocab_ok = vocab_n = 0
    for doc, facts in EVAL["docs"].items():
        ex = run.get(doc, [])
        ex_vals = [(first_float(e["value"]), e.get("catalogue_key", "none")) for e in ex]
        ex_vals = [(v, k) for v, k in ex_vals if v is not None]
        for f in facts:
            b = f["bucket"]
            tally[b]["n"] += 1
            hits = [k for v, k in ex_vals if value_match(f["value"], v)]
            if hits:
                tally[b]["hit"] += 1
                vocab_n += 1
                vocab_ok += any(acceptable_key(f["key"], k) for k in hits)

    # hallucination + volume
    total_f = halluc = nonekey = 0
    for doc in EVAL["docs"]:
        text = (TEXTDIR / f"{doc}.txt").read_text()
        digits = re.sub(r"[,\s]", "", text)
        for e in run.get(doc, []):
            total_f += 1
            nonekey += e.get("catalogue_key", "none") == "none"
            raw = str(e["value"]).replace("$", "").replace("%", "").strip()
            if not (raw in text or raw.replace(",", "") in digits or raw in re.sub(r"\s", "", text)):
                halluc += 1

    n = sum(t["n"] for t in tally.values())
    hit = sum(t["hit"] for t in tally.values())
    print(f"\n=== {label} ===")
    for b in buckets:
        t = tally[b]
        print(f"  recall {b:16} {t['hit']:>3}/{t['n']:<3} ({100*t['hit']//max(t['n'],1)}%)")
    print(f"  recall {'OVERALL':16} {hit:>3}/{n:<3} ({100*hit//max(n,1)}%)")
    print(f"  vocab accuracy        {vocab_ok}/{vocab_n} ({100*vocab_ok//max(vocab_n,1)}%) of matched facts carry an acceptable key")
    print(f"  facts emitted         {total_f}  ({nonekey} key='none', {halluc} value-not-in-source)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--regex", action="store_true")
    ap.add_argument("--facts")
    ap.add_argument("--label", default=None)
    a = ap.parse_args()
    if a.regex:
        score(regex_run(), "REGEX pipeline")
    elif a.facts:
        score(load_run(a.facts), a.label or Path(a.facts).stem)
    else:
        ap.error("pass --regex or --facts PATH")
