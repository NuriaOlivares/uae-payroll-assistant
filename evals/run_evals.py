#!/usr/bin/env python3
"""Run the seed questions through the assistant and print a score table.

Usage (from the repo root):
    python evals/run_evals.py                  # all items without 'todo' sources, with LLM judge
    python evals/run_evals.py --no-judge       # automatic checks only (cheaper, no fact grading)
    python evals/run_evals.py --only fact-01,num-03
    python evals/run_evals.py --file evals/heldout_questions.json   # held-out: final reporting only
Results are saved to evals/results/run-<timestamp>.json.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SEED = ROOT / "evals" / "seed_questions.json"
RESULTS_DIR = ROOT / "evals" / "results"

ABSTAIN_RE = re.compile(
    r"not sure|do(?:es)? not (?:have|cover|contain)|don't have|cannot (?:answer|find|determine)"
    r"|can't (?:answer|find|determine)|no information|not covered|outside (?:my|the|of)|doesn't cover"
    r"|isn't covered|not (?:included|available) in", re.IGNORECASE)
NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
CITE_RE = re.compile(r"\[([^\]]+)\]")
PAIR_RE = re.compile(r"([A-Z]{2,3} \d+/\d{4}), Art\. (\d+)")


def run_ask(question):
    from app.answer import ask
    return ask(question)


def _parse_flags(text, n):
    """Fallback: find a bracketed list of n booleans anywhere in the reply."""
    for m in re.finditer(r"\[[^\[\]]*\]", text):
        try:
            flags = json.loads(m.group(0).lower())  # also accepts True/False
        except ValueError:
            continue
        if isinstance(flags, list) and len(flags) == n and all(isinstance(x, bool) for x in flags):
            return flags
    return None


def judge(item, answer):
    """LLM judge: ask for a structured tool call, fall back to parsing the text, retry once."""
    facts = item.get("required_facts", [])
    if not facts:
        return None
    from app.answer import MODEL, _anthropic
    numbered = "\n".join(f"{i + 1}. {f}" for i, f in enumerate(facts))
    prompt = ("You grade an assistant's answer against required facts.\n"
              f"Question: {item['question']}\n\nAnswer:\n{answer}\n\nRequired facts:\n{numbered}\n\n"
              "For each fact, report true only if the answer clearly states it (or, for a behavior, "
              "clearly does it). You MUST call the grade tool with one boolean per fact, in order. "
              "Do not write anything else.")
    tool = {"name": "grade", "description": "One boolean per required fact, in order.",
            "input_schema": {"type": "object",
                             "properties": {"verdicts": {"type": "array", "items": {"type": "boolean"}}},
                             "required": ["verdicts"]}}
    for _attempt in range(2):
        resp = _anthropic().messages.create(model=MODEL, max_tokens=500, tools=[tool],
                                            messages=[{"role": "user", "content": prompt}])
        for block in resp.content:
            if block.type == "tool_use":
                flags = block.input.get("verdicts")
                if isinstance(flags, list) and len(flags) == len(facts) and all(isinstance(x, bool) for x in flags):
                    return flags
        text = "".join(b.text for b in resp.content if b.type == "text")
        flags = _parse_flags(text, len(facts))
        if flags is not None:
            return flags
    print("        judge reply unusable")
    return None
    
def short_for(doc):
    """'Cabinet Resolution No. 1 of 2022 (...)' -> 'CR 1/2022' (matches the --short used at ingest)."""
    m = re.search(r"(\d+)\s*(?:of|/)\s*(\d{4})", doc)
    if not m:
        return None
    return f"{'CR' if 'cabinet' in doc.lower() else 'FDL'} {m.group(1)}/{m.group(2)}"


def expected_refs(item):
    refs = set()
    for s in item.get("sources", []):
        if s.get("status") != "verified":
            continue
        short = short_for(s.get("doc", ""))
        if not short:
            continue
        for part in re.split(r"[,;]", s.get("article", "")):
            m = re.match(r"\s*(\d+)", part)
            if m:
                refs.add((short, int(m.group(1))))
    return refs


def evaluate(item, result, use_judge):
    answer = result["answer"]
    checks = {}
    if item.get("should_abstain"):
        checks["abstained"] = bool(ABSTAIN_RE.search(answer))
    else:
        has_cites = bool(CITE_RE.search(answer))
        checks["no_over_abstain"] = has_cites or not answer.strip().lower().startswith("i'm not sure")
        refs = expected_refs(item)
        if refs:
            retrieved = {(a, int(b)) for c in result["retrieved"] for a, b in PAIR_RE.findall(c["citation"])}
            cited = {(a, int(b)) for lbl in CITE_RE.findall(answer) for a, b in PAIR_RE.findall(lbl)}
            checks["cites_expected"] = bool(cited & refs)
            checks["no_fake_citations"] = cited <= retrieved
            checks["retrieval_recall"] = len(retrieved & refs) / len(refs)
    expected = item.get("expected_value")
    if expected is not None:
        tol = item.get("tolerance") or 0
        nums = [float(n.replace(",", "")) for n in NUM_RE.findall(answer) if n.replace(",", "").replace(".", "").isdigit()]
        checks["numeric_match"] = any(abs(n - expected) <= tol for n in nums)
    if "calculation" in item:
        checks["used_tool"] = bool(result["tool_calls"])
    if use_judge and item.get("required_facts"):
        flags = judge(item, answer)
        if flags is None:
            checks["judge_ok"] = False  # unparseable judge reply counts as a failure
        else:
            checks["facts_covered"] = sum(flags) / len(flags)
            checks["missed_facts"] = [f for f, ok in zip(item["required_facts"], flags) if not ok]
    return checks


def is_pass(checks):
    for k, v in checks.items():
        if k == "retrieval_recall":
            continue  # diagnostic only, not a pass/fail gate
        if v is False or (k == "facts_covered" and v < 1.0):
            return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--include-todo", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--file", type=Path, default=SEED,
                    help="question file (default: seed_questions.json; held-out: evals/heldout_questions.json)")
    args = ap.parse_args()

    items = json.loads(args.file.read_text(encoding="utf-8"))["items"]
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    if only:
        items = [i for i in items if i["id"] in only]
    skipped = []
    if not args.include_todo:
        skipped = [i["id"] for i in items if any(s.get("status") == "todo" for s in i.get("sources", []))]
        items = [i for i in items if i["id"] not in skipped]

    rows = []
    for item in items:
        try:
            result = run_ask(item["question"])
            checks = evaluate(item, result, not args.no_judge)
            rows.append({"id": item["id"], "category": item["category"], "checks": checks,
                         "passed": is_pass(checks), "answer": result["answer"],
                         "retrieved": [c["citation"] for c in result["retrieved"]],
                         "tool_calls": result["tool_calls"]})
        except Exception as e:  # keep going; a crash is a failed item, not a failed run
            rows.append({"id": item["id"], "category": item["category"], "checks": {},
                         "passed": False, "error": repr(e)})
        r = rows[-1]
        failed = [k for k, v in r["checks"].items()
                  if k != "retrieval_recall" and (v is False or (k == "facts_covered" and v < 1))]
        print(f"{'PASS' if r['passed'] else 'FAIL'}  {r['id']:<9} {', '.join(failed) or r.get('error', '')}")
        for f in r["checks"].get("missed_facts", []):
            print("        missed:", f)

    # ---- summary ----
    print("\n| category | passed | total |\n|---|---|---|")
    for cat in sorted({r["category"] for r in rows}):
        sub = [r for r in rows if r["category"] == cat]
        print(f"| {cat} | {sum(r['passed'] for r in sub)} | {len(sub)} |")
    total_pass = sum(r["passed"] for r in rows)
    print(f"\nOverall: {total_pass}/{len(rows)} passed ({100 * total_pass / max(len(rows), 1):.0f}%)")

    def mean(key):
        vals = [float(r["checks"][key]) for r in rows if key in r["checks"]]
        return f"{100 * sum(vals) / len(vals):.0f}% ({len(vals)} items)" if vals else "n/a"
    for label, key in [("Retrieval recall", "retrieval_recall"), ("Cites expected article", "cites_expected"),
                       ("No fake citations", "no_fake_citations"), ("Numeric exact match", "numeric_match"),
                       ("Used calculator tool", "used_tool"), ("Abstained when it should", "abstained"),
                       ("Required-fact coverage", "facts_covered")]:
        print(f"{label}: {mean(key)}")
    if skipped:
        print(f"Skipped (unverified sources): {skipped}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    tag = "" if args.file.resolve() == SEED.resolve() else f"{args.file.stem}-"
    out = RESULTS_DIR / f"run-{tag}{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {out}")


if __name__ == "__main__":
    main()