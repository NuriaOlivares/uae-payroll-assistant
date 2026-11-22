#!/usr/bin/env python3
"""Free retrieval-only eval: uses the local index only, no LLM calls, no API cost.

For every non-abstention question with verified article references, report at which rank
each expected article appears, then recall for several values of k.

Usage (repo root):  python evals/run_retrieval.py [--ks 3,5,8,10,15]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_evals import PAIR_RE, SEED, expected_refs  # noqa: E402


def retrieve(question, k):
    from app.answer import retrieve as _retrieve
    return _retrieve(question, k)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ks", default="3,5,8,10,15")
    args = ap.parse_args()
    ks = sorted(int(x) for x in args.ks.split(","))

    items = json.loads(Path(SEED).read_text(encoding="utf-8"))["items"]
    rows = []
    for item in items:
        refs = expected_refs(item)
        if item.get("should_abstain") or not refs:
            continue
        ranks = {}
        for rank, chunk in enumerate(retrieve(item["question"], max(ks)), 1):
            for a, b in PAIR_RE.findall(chunk["citation"]):
                ref = (a, int(b))
                if ref in refs and ref not in ranks:
                    ranks[ref] = rank
        rows.append((item["id"], refs, ranks))

    print("Rank of each expected article (- = not in top %d):" % max(ks))
    for id_, refs, ranks in rows:
        shown = ", ".join(f"{a} Art.{n}: {ranks.get((a, n), '-')}" for a, n in sorted(refs))
        print(f"  {id_:<9} {shown}")

    print("\n| k | mean recall | questions fully covered |\n|---|---|---|")
    for k in ks:
        recalls = [sum(1 for r in refs if ranks.get(r, 10**6) <= k) / len(refs) for _, refs, ranks in rows]
        full = sum(1 for x in recalls if x == 1)
        print(f"| {k} | {100 * sum(recalls) / len(recalls):.0f}% | {full}/{len(rows)} |")


if __name__ == "__main__":
    main()