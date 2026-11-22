#!/usr/bin/env python3
"""Split a legal PDF into article-level chunks that keep their citation.

Usage (from the repo root):
    pip install pdfplumber
    python ingest.py data/raw/decree_law_33_2021.pdf \
        --doc-id fdl-33-2021 \
        --doc-title "Federal Decree-Law No. 33 of 2021 (as amended)" \
        --short "FDL 33/2021"

Output: data/processed/<doc-id>.jsonl, one chunk per line.
Always read the printed report and spot-check a few articles with --show.
"""
import argparse
import bisect
import json
import re
import statistics
from datetime import date
from pathlib import Path

import pdfplumber

# "Article (29)" at the start of a line, optionally followed by the title.
# Some PDF pages extract with mirrored brackets ("Article )2(", "Article) 7("), so accept
# either bracket on both sides.
ARTICLE_RE = re.compile(r"^[ \t]*Article[ \t]*[()][ \t]*(\d+)[ \t]*[()][ \t]*(.*)$",
                        re.MULTILINE | re.IGNORECASE)
# Top-level clause numbers at the start of a line: "1." or "1)".
CLAUSE_RE = re.compile(r"^[ \t]*(\d{1,2})[ \t]*[.)][ \t]+", re.MULTILINE)
# A line that starts like this is a cross-reference inside a sentence, not a heading.
CROSS_REF_START = re.compile(
    r"^(of|and|or|to|in|shall|hereof|above|herein|from|under|pursuant|stated|referred)\b",
    re.IGNORECASE)
ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
FOOTER_RE = re.compile(
    r"^(Federal Decree[- ]by[- ]Law|Federal Decree[- ]Law|Cabinet Resolution)\b.{0,150}\s\d{1,3}$",
    re.IGNORECASE)


def extract_pages(pdf_path):
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return pages


def clean_text(text, drop_arabic=True):
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.fullmatch(r"\d{1,4}", stripped):  # bare page number
            continue
        if drop_arabic:
            letters = [c for c in stripped if c.isalpha()]
            if letters and sum(bool(ARABIC_RE.match(c)) for c in letters) / len(letters) > 0.3:
                continue
        if FOOTER_RE.match(stripped):  # running footer with page number
            continue
        lines.append(re.sub(r"[ \t]+", " ", stripped))
    return "\n".join(lines)


def find_headings(text):
    headings = []
    for m in ARTICLE_RE.finditer(text):
        title = m.group(2).strip()
        if len(title) > 80 or CROSS_REF_START.match(title):
            continue
        headings.append((m.start(), m.end(), int(m.group(1)), title))
    return headings


def split_articles(text):
    """Return {article_number: (title, body, start_offset)}, keeping the longest body
    when a number appears more than once (table of contents entries are short)."""
    headings = find_headings(text)
    candidates = {}
    for i, (start, end, number, title) in enumerate(headings):
        next_start = headings[i + 1][0] if i + 1 < len(headings) else len(text)
        body = text[end:next_start].strip()
        candidates.setdefault(number, []).append((title, body, start))
    articles, warnings = {}, []
    for number, options in candidates.items():
        options.sort(key=lambda o: len(o[1]), reverse=True)
        if len(options) > 1 and len(options[1][1]) > 200:
            warnings.append(f"Article {number} has {len(options)} long candidates; check it manually")
        title, body, start = options[0]
        if not title:
            first, _, rest = body.partition("\n")
            if first and len(first) <= 60 and not re.match(r"\d", first) \
                    and not first.rstrip().endswith((".", ":", ";", ",")):
                title, body = first.strip(), rest.strip()
        articles[number] = (title, body, start)
    return articles, warnings


def split_clauses(body, max_chars):
    """Group top-level clauses into chunks under max_chars. Returns [(label, text)]."""
    if len(body) <= max_chars:
        return [("", body)]
    matches = [m for m in CLAUSE_RE.finditer(body)]
    # keep only the clause numbers that form the sequence 1, 2, 3, ...
    clauses, expected = [], 1
    for m in matches:
        if int(m.group(1)) == expected:
            clauses.append((expected, m.start()))
            expected += 1
    if len(clauses) < 2:
        return [("", body)]
    preamble = body[:clauses[0][1]].strip()
    pieces = []
    for i, (num, start) in enumerate(clauses):
        end = clauses[i + 1][1] if i + 1 < len(clauses) else len(body)
        pieces.append((num, body[start:end].strip()))
    groups, current = [], []
    for num, text in pieces:
        if current and sum(len(t) for _, t in current) + len(text) > max_chars:
            groups.append(current)
            current = []
        current.append((num, text))
    if current:
        groups.append(current)
    result = []
    for g_index, group in enumerate(groups):
        first, last = group[0][0], group[-1][0]
        label = f"({first})" if first == last else f"({first})-({last})"
        text = "\n".join(t for _, t in group)
        if g_index == 0 and preamble:
            text = preamble + "\n" + text
        result.append((label, text))
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--doc-id", required=True)
    ap.add_argument("--doc-title", required=True)
    ap.add_argument("--short", required=True, help="short citation name, e.g. 'FDL 33/2021'")
    ap.add_argument("--jurisdiction", default="federal")
    ap.add_argument("--out-dir", default="data/processed")
    ap.add_argument("--max-chars", type=int, default=1800)
    ap.add_argument("--keep-arabic", action="store_true")
    ap.add_argument("--show", default="", help="comma-separated article numbers to print")
    args = ap.parse_args()

    pages = [clean_text(p, drop_arabic=not args.keep_arabic) for p in extract_pages(args.pdf)]
    page_starts, text, offset = [], "", 0
    for p in pages:
        page_starts.append(offset)
        text += p + "\n"
        offset += len(p) + 1

    articles, warnings = split_articles(text)
    if not articles:
        raise SystemExit("No 'Article (N)' headings found. Check the PDF text with pdfplumber first.")

    chunks = []
    for number in sorted(articles):
        title, body, start = articles[number]
        page = bisect.bisect_right(page_starts, start)  # 1-based page number
        for label, chunk_text in split_clauses(body, args.max_chars):
            citation = f"{args.short}, Art. {number}{label}"
            header = f"{citation}" + (f" - {title}" if title else "")
            chunks.append({
                "id": f"{args.doc_id}-a{number}{label.replace(' ', '')}",
                "doc_id": args.doc_id,
                "doc_title": args.doc_title,
                "jurisdiction": args.jurisdiction,
                "article": number,
                "clause": label.strip("()") if label else None,
                "title": title,
                "citation": citation,
                "page_start": page,
                "source_file": Path(args.pdf).name,
                "ingested_on": date.today().isoformat(),
                "text": f"{header}\n{chunk_text}",
            })

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.doc_id}.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # ---- report: read this before trusting the output ----
    numbers = sorted(articles)
    missing = [n for n in range(1, numbers[-1] + 1) if n not in articles]
    lengths = [len(c["text"]) for c in chunks]
    short = [n for n in numbers if len(articles[n][1]) < 80]
    print(f"Wrote {len(chunks)} chunks from {len(numbers)} articles to {out_path}")
    print(f"Articles found: {numbers[0]}-{numbers[-1]}; missing numbers: {missing or 'none'}")
    print(f"Chunk length (chars): min {min(lengths)}, median {int(statistics.median(lengths))}, max {max(lengths)}")
    if short:
        print(f"Very short bodies (heading probably mis-parsed): {short}")
    for w in warnings:
        print("WARNING:", w)
    for n in [int(x) for x in args.show.split(",") if x.strip()]:
        if n in articles:
            print(f"\n=== Article {n} ({articles[n][0]}) ===\n{articles[n][1][:1500]}")
        else:
            print(f"\n=== Article {n}: not found ===")


if __name__ == "__main__":
    main()