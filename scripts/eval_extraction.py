"""Score an extraction run against tests/golden/extraction_eval.yml.

Usage:
  .venv/bin/python scripts/eval_extraction.py --regex
  .venv/bin/python scripts/eval_extraction.py --facts run.json [--label NAME] [--gate]

Reports BOTH a loose recall (value-only — optimistic) and a STRICT recall (value +
acceptable key, matched 1:1 so duplicate values can't double-count), plus contradictions
(model claimed an evaluated key with the WRONG value), coverage accuracy, and hallucination
(value not verbatim in source). With --gate it exits non-zero if the acceptance criteria fail.

Corpus resolution: prefer data/processed/text (local), else tests/golden/fixtures (committed,
so the eval and its tests run on a fresh checkout / CI). `compute(run)` is importable for tests.

Caveats this harness does NOT yet remove (see docs/extraction_eval_loop.md):
  - one filing only; eval values partly LLM-derived then spot-checked, not fully hand-labelled;
  - LLM runs are non-deterministic (single sample); few-shot examples overlap the eval docs.
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
_REAL = ROOT / "data/processed/text"
TEXTDIR = _REAL if _REAL.exists() else (ROOT / "tests/golden/fixtures")
EVAL = yaml.safe_load((ROOT / "tests/golden/extraction_eval.yml").read_text())
ALIASES = EVAL.get("key_aliases", {})
HELDOUT = set(EVAL.get("heldout_docs", []))

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


def compute(run):
    """Return the metrics dict for an extraction run. Importable for tests."""
    buckets = ["labeled_scalar", "labeled_series", "grid_cell"]
    loose = {b: [0, 0] for b in buckets}
    strict = {b: [0, 0] for b in buckets}
    contradictions = []
    cov_ok = cov_n = vocab_ok = vocab_n = 0
    split = {"in_prompt": [0, 0], "heldout": [0, 0]}  # [strict_hit, n] — generalisation check
    for doc, evals in EVAL["docs"].items():
        sp = "heldout" if doc in HELDOUT else "in_prompt"
        ex = [{"v": first_float(e["value"]), "k": e.get("catalogue_key", "none"), "c": norm_cov(e.get("coverage"))}
              for e in run.get(doc, [])]
        ex = [e for e in ex if e["v"] is not None]
        used = set()
        for f in evals:
            b = f["bucket"]
            loose[b][1] += 1
            strict[b][1] += 1
            split[sp][1] += 1
            ev, ek, ec = f["value"], f["key"], f.get("coverage")
            if any(vmatch(ev, e["v"]) for e in ex):
                loose[b][0] += 1
            cand = [i for i, e in enumerate(ex) if i not in used and vmatch(ev, e["v"]) and acceptable_key(ek, e["k"])]
            if cand:
                i = cand[0]
                used.add(i)
                strict[b][0] += 1
                split[sp][0] += 1
                vocab_ok += 1
                vocab_n += 1
                if ec and ec != "none":
                    cov_n += 1
                    cov_ok += (ex[i]["c"] == ec)
            else:
                wrong = [e for e in ex if acceptable_key(ek, e["k"]) and not vmatch(ev, e["v"])]
                if wrong:
                    contradictions.append(f"{doc}: {ek}={ev} but model emitted {ek}={wrong[0]['v']}")
                if any(vmatch(ev, e["v"]) for e in ex):
                    vocab_n += 1
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
    n = sum(loose[b][1] for b in buckets)
    return {
        "buckets": buckets, "loose": loose, "strict": strict, "n": n,
        "loose_hit": sum(loose[b][0] for b in buckets), "strict_hit": sum(strict[b][0] for b in buckets),
        "strict_recall": sum(strict[b][0] for b in buckets) / max(n, 1),
        "vocab_ok": vocab_ok, "vocab_n": vocab_n, "vocab_accuracy": vocab_ok / max(vocab_n, 1),
        "cov_ok": cov_ok, "cov_n": cov_n, "contradictions": contradictions,
        "emitted": total_f, "nonekey": nonekey, "hallucination": halluc, "split": split,
    }


def score(run, label, gate=False):
    m = compute(run)
    print(f"\n=== {label} ===")
    print(f"  loose recall (value-only)   {m['loose_hit']}/{m['n']} ({100*m['loose_hit']//max(m['n'],1)}%)   <- optimistic")
    for b in m["buckets"]:
        print(f"    strict {b:16} {m['strict'][b][0]:>3}/{m['strict'][b][1]:<3}")
    print(f"  STRICT recall (value+key)   {m['strict_hit']}/{m['n']} ({int(100*m['strict_recall'])}%)   <- trustworthy")
    sp = m["split"]
    ip = 100 * sp["in_prompt"][0] // max(sp["in_prompt"][1], 1)
    ho = 100 * sp["heldout"][0] // max(sp["heldout"][1], 1)
    print(f"  strict by split             in-prompt {sp['in_prompt'][0]}/{sp['in_prompt'][1]} ({ip}%)  held-out {sp['heldout'][0]}/{sp['heldout'][1]} ({ho}%)  <- generalisation")
    print(f"  vocab accuracy              {m['vocab_ok']}/{m['vocab_n']} ({int(100*m['vocab_accuracy'])}%)")
    print(f"  coverage accuracy           {m['cov_ok']}/{m['cov_n']} (among strict matches)")
    print(f"  contradictions (wrong value){len(m['contradictions']):>3}")
    for c in m["contradictions"][:8]:
        print(f"      - {c}")
    print(f"  facts emitted               {m['emitted']}  ({m['nonekey']} key='none', {m['hallucination']} value-not-in-source)")
    if gate:
        fails = []
        if m["strict_recall"] < ACCEPT["strict_recall"]:
            fails.append(f"strict_recall {m['strict_recall']:.2f} < {ACCEPT['strict_recall']}")
        if m["vocab_accuracy"] < ACCEPT["vocab_accuracy"]:
            fails.append(f"vocab_accuracy {m['vocab_accuracy']:.2f} < {ACCEPT['vocab_accuracy']}")
        if len(m["contradictions"]) > ACCEPT["max_contradictions"]:
            fails.append(f"contradictions {len(m['contradictions'])} > {ACCEPT['max_contradictions']}")
        if m["hallucination"] > ACCEPT["max_hallucination"]:
            fails.append(f"hallucination {m['hallucination']} > {ACCEPT['max_hallucination']}")
        print(("\n  GATE: FAIL — " + "; ".join(fails)) if fails else "\n  GATE: PASS")
        return 1 if fails else 0
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
