"""Score the SERFF extractors against the golden anchor set (precision/recall/review-rate).

Run:  .venv/bin/python scripts/score_extraction.py
This is the measurement backbone of the build->test->improve loop. It does NOT modify
anything; it reports how close extraction is to the golden facts an actuary expects.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from serff_intel.extract.rate_impact import extract_rate_facts
from serff_intel.extract.actuarial_reasons import extract_reason_facts
from serff_intel.extract.objections import extract_objection_facts

ROOT = Path(__file__).resolve().parents[1]
TEXTDIR = ROOT / "data/processed/text"
GOLDEN = yaml.safe_load((ROOT / "tests/golden/expected_facts.yml").read_text())


def _num(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = value.replace("$", "").replace(",", "").replace("%", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _facts(doc: str):
    text = (TEXTDIR / f"{doc}.txt").read_text()
    return extract_rate_facts(text) + extract_reason_facts(text) + extract_objection_facts(text)


def _matches(facts, key: str, value=None) -> bool:
    for f in facts:
        if key not in (f.fact_key, f.fact_type):
            continue
        if value is None:
            return True
        fv = _num(f.normalized_value)
        if fv is not None and abs(fv - float(value)) < 0.01:
            return True
    return False


def main() -> None:
    facts_by_doc = {doc: _facts(doc) for doc in set(GOLDEN["anchors"]) | set(GOLDEN.get("must_not", {}))}

    prose_hit = prose_tot = tbl_hit = tbl_tot = 0
    misses: list[str] = []
    for doc, anchors in GOLDEN["anchors"].items():
        facts = facts_by_doc[doc]
        for a in anchors:
            ok = _matches(facts, a["key"], a.get("value"))
            if a.get("table_borne"):
                tbl_tot += 1
                tbl_hit += ok
            else:
                prose_tot += 1
                prose_hit += ok
            if not ok:
                misses.append(f"{doc}: {a['key']}={a.get('value')}" + (" [table]" if a.get("table_borne") else ""))

    fp_pass = fp_tot = 0
    fp_fail: list[str] = []
    for doc, checks in GOLDEN.get("must_not", {}).items():
        facts = facts_by_doc[doc]
        for c in checks:
            fp_tot += 1
            violated = _matches(facts, c["key"], c.get("value"))
            fp_pass += not violated
            if violated:
                fp_fail.append(f"{doc}: must NOT have {c['key']}={c.get('value')}")

    anchor_docs = list(GOLDEN["anchors"])
    all_facts = [f for doc in anchor_docs for f in facts_by_doc[doc]]
    need_rev = sum(1 for f in all_facts if getattr(f, "needs_review", False))

    print("=" * 60)
    print("SERFF EXTRACTION SCOREBOARD")
    print("=" * 60)
    print(f"  Prose recall          {prose_hit}/{prose_tot}  ({100*prose_hit//max(prose_tot,1)}%)")
    print(f"  Table-borne recall    {tbl_hit}/{tbl_tot}  ({100*tbl_hit//max(tbl_tot,1)}%)  [known gap]")
    print(f"  Overall recall        {prose_hit+tbl_hit}/{prose_tot+tbl_tot}")
    print(f"  False-positive guards {fp_pass}/{fp_tot} passing")
    print(f"  Review rate           {need_rev}/{len(all_facts)} facts flagged ({100*need_rev//max(len(all_facts),1)}%)")
    if misses:
        print("\n  MISSED anchors:")
        for m in misses:
            print(f"    - {m}")
    if fp_fail:
        print("\n  FALSE POSITIVES:")
        for m in fp_fail:
            print(f"    - {m}")


if __name__ == "__main__":
    main()
