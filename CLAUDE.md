# UAE Payroll & Employment Assistant

RAG assistant that answers UAE federal private-sector employment questions with article-level citations, does calculations with tools (never the model), and abstains when the sources don't cover the question. It is a portfolio project for applied AI / forward-deployed AI engineer applications. The owner must be able to explain every design decision in interviews, so briefly explain the reasoning and trade-offs behind changes. Not legal advice.

## Commands
- Install: `pip install -r requirements.txt` (key in `.env`: `ANTHROPIC_API_KEY`, optional `TOP_K`, `ANSWER_MODEL`)
- Ingest one PDF: `python pipeline/ingest.py data/raw/<file>.pdf --doc-id <id> --doc-title "<title>" --short "<short>"`
  - Documents (`--doc-id` / `--short`): `fdl-33-2021` / "FDL 33/2021", `cr-1-2022` / "CR 1/2022", `cr-27-2024` / "CR 27/2024", `cr-97-2022` / "CR 97/2022", `fdl-13-2022` / "FDL 13/2022"
- Build index: `python pipeline/build_index.py` (rebuilds `data/index/` from `data/processed/*.jsonl`)
- Ask: `python -m app.answer "question"`; API: `uvicorn app.main:app --reload`
- Unit tests: `pytest`
- FREE retrieval-only eval (no API calls): `python evals/run_retrieval.py`
- Full eval (calls the model and a judge, costs credits): `TOP_K=10 python evals/run_evals.py` (`--only id1,id2`, `--no-judge`)
- Print saved answers from the latest eval run (free): `python scripts/show_answers.py <test ids>`

## Structure
`pipeline/` ingest.py, build_index.py | `app/` answer.py (retrieve + answer loop), tools.py (gratuity, leave calculators), main.py (FastAPI) | `evals/` seed_questions.json, run_evals.py, run_retrieval.py, results/, heldout_questions.json, RESULTS.md (experiment log) | `data/raw|processed|index` | `README.md`

## Rules
- **Cost:** evals call the API. Prefer `run_retrieval.py` and `--only`. Run the full eval only when asked, and never re-run it repeatedly to get a better score.
- **Tests are not tuned to pass.** Edit `evals/seed_questions.json` only when a test is wrong (a required fact the retrieved sources can't support, or the wrong source). Log every change in the "Test changes" table of `evals/RESULTS.md` with the date and reason. Required facts must be supportable from the corpus.
- **One change at a time.** Log each run as a new row in `evals/RESULTS.md` (change, scores, notes). Never edit past rows. Report development and held-out scores separately.
- **Don't invent legal facts.** Check article numbers against the official text. Mark anything unverified as `todo`.
- **Calculations stay in `app/tools.py`** with unit tests in `tests/`.
- **Citation format is a contract:** chunk citations look like `FDL 33/2021, Art. 29(1)-(2)` and `run_evals.py` parses them (`PAIR_RE`). Don't change the format without updating the evals.
- **Model API limits:** this model rejects `temperature` and forced `tool_choice`. Don't add them. The judge uses an optional tool call, a text fallback parser and one retry.
- Terminal commands for the owner (macOS zsh): give them unindented, especially `python - << 'EOF'` blocks.
- Don't commit `.env`, `data/index/`, or `evals/results/`.

## Data quirks
- Some Decree-Law pages extract with mirrored brackets (`Article )2(`); `ARTICLE_RE` in `ingest.py` accepts both bracket orders.
- Running page footers leak into chunks; `FOOTER_RE` in `ingest.py` strips them.
- FDL 13/2022 has no Article 1 chunk in the index (harmless so far).
- `TOP_K` defaults to 10 in `app/answer.py` (changed 2026-11-22; eval runs set it explicitly).

## Current state (2026-11-22)
- Development set (18 questions): 18/18 at k=10 (R4); 15/18 at k=5 (R3). Not a clean k comparison: the judge and two tests changed between them (see evals/RESULTS.md). These are not held-out scores.
- Held-out set: 12 questions in `evals/heldout_questions.json` (2026-11-22), not yet run. Run once with `--file` for final reporting only.
- Retrieval-only recall (13 questions): k=5 85%, k=10 96%.
- Weak spots: FDL 13/2022 Art. 5 and 6 rank 7th and 9th for the unemployment question; FDL 33/2021 Art. 6 ranks 9th for the visa question ("sponsor visas" vs "work permit"). k=10 only just catches them.
- The judge is the same model family as the generator and is noisy.

## Next tasks (in this order)
1. ~~Write about 10 held-out questions in `evals/heldout_questions.json` (paraphrases, two-article questions, gratuity above 5 years, traps that must abstain or decline). Add a `--file` option to `run_evals.py`. Questions are written before seeing results.~~ (done 2026-11-22; owner review, then one run)
2. Re-ranking: retrieve about 20, re-rank locally with a small cross-encoder, send the best 5. Measure with `run_retrieval.py` first (free).
3. If recall problems remain: query rewriting into legal terms, hybrid keyword + embedding search.
4. Hijri-to-Gregorian date tool for approximate holiday dates (moon sighting can shift by a day).
5. Add the official public-holidays government page to the corpus; later DIFC as a second jurisdiction with metadata filtering.
6. ~~README: example answer, `TOP_K` default 10~~ (done 2026-11-22).
