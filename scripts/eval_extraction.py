"""Score an extraction run against tests/golden/extraction_eval.yml.

Usage:
  .venv/bin/python scripts/eval_extraction.py --regex
  .venv/bin/python scripts/eval_extraction.py --facts run.json [--label NAME] [--gate]

Reports BOTH a loose recall (value-only — the optimistic number) and a STRICT recall
(value + acceptable key, matched 1:1 so duplicate values can't double-count), plus:
  - contradictions: the model claimed an evaluated (key) slot with the WRONG value
    (this is what catches e.g. permissible_loss_ratio=100 from the "100% - (9) 58.1%" line);
  - coverage accuracy among strict matches;
  - hallucination: emitted value not present verbatim in source.
With --gate it exits non-zero if the acceptance criteria are not met (CI-style verifiability).

Caveats this harness does NOT yet remove (see docs/extraction_eval_loop.md):
  - one filing only; eval values partly LLM-derived then spot-checked, not fully hand-labelled;
  - LLM runs are non-deterministic (this is a single sample); few-shot examples overlap the eval docs.
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
TEXTDIR = ROOT / "data/processed/text"
EVAL = yaml.safe_load((ROOT / "tests/golden/extraction_eval.yml").read_text())
ALIASES = EVAL.get("key_aliases", {})

# Acceptance criteria (the bar an extraction run must clear under --gate).
ACCEPT = {"strict_recall": 0.90, "vocab_accuracy": 0.90, "max_contradictions": 0, "max_hallucination": 0}

_COV = {
    "liability": "AL", "auto liability": "AL", "commercial auto liability": "AL", "al": "AL",
    "physical damage": "APD", "auto physical damage": "APD", "apd": "APD",
    "bodily injury": "BI", "bi": "BI", "property damage": "PD", "pd": "PD",
}


def norm_cov(c):
    c = (c or "").strip().lower()
    for k, v in _COV.items():
        if k in c:
            return v
    return None


def first_float(s):
    if s is None:
        return None
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(s).replace("$", ""))
    try:
        return float(m.group(0).replace(",", "")) if m else None
    except ValueError:
        return None


def vmatch(a, b):
    return abs(a - b) <= max(0.05, abs(b) * 0.001)


def acceptable_key(expected, got):
    return got == expected or got in ALIASES.get(expected, [expected])


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
        out[doc] = [{"catalogue_key": f.fact_key or f.fact_type, "value": f.normalized_value, "coverage": f.coverage} for f in facts]
    return out


def score(run, label, gate=False):
    if not TEXTDIR.exists():
        print("SKIP: processed corpus not present (gitignored).")
        return 0
    buckets = ["labeled_scalar", "labeled_series", "grid_cell"]
    loose = {b: [0, 0] for b in buckets}        # [hit, n]
    strict = {b: [0, 0] for b in buckets}
    contradictions = []
    cov_ok = cov_n = vocab_ok = vocab_n = 0

    for doc, evals in EVAL["docs"].items():
        ex = [{"v": first_float(e["value"]), "k": e.get("catalogue_key", "none"), "c": norm_cov(e.get("coverage"))}
              for e in run.get(doc, [])]
        ex = [e for e in ex if e["v"] is not None]
        used = set()
        for f in evals:
            b = f["bucket"]
            loose[b][1] += 1
            strict[b][1] += 1
            ev, ek, ec = f["value"], f["key"], f.get("coverage")
            # loose: any value match
            if any(vmatch(ev, e["v"]) for e in ex):
                loose[b][0] += 1
            # strict: unused fact with value match AND acceptable key, matched 1:1
            cand = [i for i, e in enumerate(ex) if i not in used and vmatch(ev, e["v"]) and acceptable_key(ek, e["k"])]
            if cand:
                i = cand[0]
                used.add(i)
                strict[b][0] += 1
                vocab_n += 1
                vocab_ok += 1
                if ec and ec != "none":
                    cov_n += 1
                    cov_ok += (ex[i]["c"] == ec)
            else:
                # contradiction: an acceptable-key fact exists for this slot but with a different value
                wrong = [e for e in ex if acceptable_key(ek, e["k"]) and not vmatch(ev, e["v"])]
                vmatch_wrongkey = [e for e in ex if vmatch(ev, e["v"])]
                if wrong and not any(vmatch(ev, e["v"]) and acceptable_key(ek, e["k"]) for e in ex):
                    contradictions.append(f"{doc}: {ek}={ev} but model emitted {ek}={wrong[0]['v']}")
                if vmatch_wrongkey and not cand:
                    vocab_n += 1  # value found but under a wrong key -> vocab miss

    # hallucination
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

    ln = sum(loose[b][1] for b in buckets)
    lh = sum(loose[b][0] for b in buckets)
    sh = sum(strict[b][0] for b in buckets)
    sr = sh / max(ln, 1)
    va = vocab_ok / max(vocab_n, 1)
    print(f"\n=== {label} ===")
    print(f"  loose recall (value-only)   {lh}/{ln} ({100*lh//ln}%)   <- optimistic")
    for b in buckets:
        print(f"    strict {b:16} {strict[b][0]:>3}/{strict[b][1]:<3}")
    print(f"  STRICT recall (value+key)   {sh}/{ln} ({100*sh//ln}%)   <- trustworthy")
    print(f"  vocab accuracy              {vocab_ok}/{vocab_n} ({100*va//1 if False else int(100*va)}%)")
    print(f"  coverage accuracy           {cov_ok}/{cov_n} (among strict matches)")
    print(f"  contradictions (wrong value){len(contradictions):>3}")
    for c in contradictions[:8]:
        print(f"      - {c}")
    print(f"  facts emitted               {total_f}  ({nonekey} key='none', {halluc} value-not-in-source)")

    if gate:
        fails = []
        if sr < ACCEPT["strict_recall"]:
            fails.append(f"strict_recall {sr:.2f} < {ACCEPT['strict_recall']}")
        if va < ACCEPT["vocab_accuracy"]:
            fails.append(f"vocab_accuracy {va:.2f} < {ACCEPT['vocab_accuracy']}")
        if len(contradictions) > ACCEPT["max_contradictions"]:
            fails.append(f"contradictions {len(contradictions)} > {ACCEPT['max_contradictions']}")
        if halluc > ACCEPT["max_hallucination"]:
            fails.append(f"hallucination {halluc} > {ACCEPT['max_hallucination']}")
        if fails:
            print("\n  GATE: FAIL — " + "; ".join(fails))
            return 1
        print("\n  GATE: PASS")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--regex", action="store_true")
    ap.add_argument("--facts")
    ap.add_argument("--label", default=None)
    ap.add_argument("--gate", action="store_true")
    a = ap.parse_args()
    if a.regex:
        sys.exit(score(regex_run(), "REGEX pipeline", a.gate))
    elif a.facts:
        sys.exit(score(load_run(a.facts), a.label or Path(a.facts).stem, a.gate))
    else:
        ap.error("pass --regex or --facts PATH")
