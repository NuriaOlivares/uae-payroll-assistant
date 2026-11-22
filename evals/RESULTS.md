# Evaluation log

One row per run. **Change one thing at a time, re-run the same tests, record the result, and never edit past rows.** If a test itself changes, log it in [Test changes](#test-changes) with the reason. A test may only change because it was wrong, never because the assistant failed it.

All scores are on the 18-question **development set** in `evals/seed_questions.json`, which was also used while building the system. They are not held-out scores (see [Held-out set](#held-out-set)).

## Setup

| Component | Value |
|---|---|
| Corpus | FDL 33/2021 (as amended), CR 1/2022, CR 27/2024, FDL 13/2022, CR 97/2022 |
| Chunking | By article, then by numbered clause when an article exceeds 1,800 characters |
| Embeddings / store | Chroma default embedding model (MiniLM), cosine distance |
| Retrieval | Top-k chunks (`TOP_K`, default 5), metadata filter `jurisdiction = federal` |
| Generator | Claude via the Anthropic API (`ANSWER_MODEL`, default `claude-sonnet-5-5`; update if you changed it) |
| Judge | Same model, grades each required fact true/false. `temperature` is not accepted by this model, so grading is not deterministic |

## Run log

| Run | Date | What changed | Overall | Retrieval recall | Cites expected article | Fact coverage | Notes |
|---|---|---|---|---|---|---|---|
| R0a | 2026-11-18 | Baseline, k=5, `--no-judge` | 16/18 (89%) | 83% | 92% | not measured | Looked good, but required facts were never checked |
| R0b | 2026-11-18 | k=5, judge on | 12/18 (67%) | 83% | 92% | 89% (17 items) | **True baseline.** R0a was inflated by skipping the fact check |
| R2a | 2026-11-18 | k=10, judge on | 14/18 (78%) | 96% | 100% | 85% (16 items) | One judge reply was unparseable and silently dropped from the averages. Not confirmed whether the over-abstain scoring fix was already applied, so the gain cannot be attributed to k alone |
| R2b | 2026-11-18 | k=10, unparseable judge replies now count as failures; missed facts printed | 12/18 (67%) | 96% | 100% | 87% (15 items) | Same system as R2a. Three items (fact-04, hol-01, hol-03) failed with `judge_ok`, meaning the judge reply could not be parsed |
| R3 | 2026-11-19 | k=5, judge parser fixed (text parser, `max_tokens=500`), test changes 1-6 applied | 15/18 (83%) | 85% (13 items) | 92% | 93% (18 items) | `run-20261119-215852`. Failed: fact-04 (recall 50%, compound fact missed), fact-05 (visa: Art. 6 not retrieved at k=5), hol-01 (missed "expected dates, not confirmed") |
| R4 | 2026-11-19 | k=10, judge switched to optional tool call + text fallback + one retry, fact-04 and hol-01 facts rewritten (test change 7) | 18/18 (100%) | 96% (13 items) | 100% | 100% (18 items) | `run-20261119-221730`. **Not a clean comparison with R3:** k, judge and two tests all changed. Preceded by three `--only fact-04,hol-01` debugging runs: `220233` and `221103` failed on facts, and `220901` crashed because the model rejects forced `tool_choice` |

**Reading the runs so far:** raising k from 5 to 10 improved retrieval recall (83-85% to 96%) and the share of answers citing an expected article (92% to 100%), and it fixed the visa question at both the R0/R2 and R3/R4 stages. The jump from 15/18 (R3) to 18/18 (R4) cannot be attributed to k alone, because the judge and two tests changed in between. A clean k comparison needs a k=5 run on the current tests and judge (proposed R5). Scores are on the development set only.

## Error analysis (latest run, R2b)

| Test | Failure | Layer | Cause | Status |
|---|---|---|---|---|
| fact-05 (visa) | Failed at k=5 (recall 0, abstained); passes at k=10 | Retrieval | "Sponsor visas" vs "work permit" wording; Art. 6 ranked too low for k=5 | Fixed by k=10 in R2a and R2b; confirm on corrected tests |
| fact-04 (unemployment) | `judge_ok`: judge reply unparseable | Scoring | Judge parser grabbed the first `[...]` in the reply, likely a citation | Fix parser, re-run. At k=5 this test failed on facts (FDL 13/2022 Art. 5 and 6 ranked 7th and 9th) |
| num-05 (working hours) | Missed fact: Article 15 and commuting time | Test | Incidental to the question, and the commuting rule is in FDL 33/2021 Art. 17(3) | Remove the fact |
| hol-01 | `judge_ok` | Scoring | Unparseable judge reply | Fix parser, re-run |
| hol-02 | Missed: moon sighting announcements; no single confirmation date | Test | Expected facts come from the u.ae page, which is not in the corpus; the holiday resolution does not say when dates are announced | Relabel as partial coverage, or add the page to the corpus |
| hol-03 | `judge_ok` | Scoring | Unparseable judge reply | Fix parser, re-run. Moon-sighting fact has the same source problem as hol-02 |
| abs-03 (desk change) | Missed: "company policy matter not covered by the legal sources" | Test or judge | Probably abstained correctly; the required fact's wording is too specific. Passed in an earlier identical run, so the judge is noisy | Read the answer, then soften the fact to "not covered by the legal sources" |

## Diagnostics

- FDL 13/2022 is indexed under the correct label. Articles present: 2-8. Article 1 (definitions) is missing, probably another heading-format quirk; harmless for the current questions.
- For "Do I have unemployment compensation?" the top-10 order was: CR 97/2022 Art. 13, 10, 12, 9, 15, 1, then FDL 13/2022 Art. 5, then FDL 33/2021 Art. 37(1)-(2), then FDL 13/2022 Art. 6, then CR 97/2022 Art. 8. At k=5 neither FDL 13/2022 article reached the model.
- `temperature=0` is rejected by the judge model, so judge variance cannot be removed that way. Plan: rerun any failing test once, and consider majority-of-3 grading later.
- Page footers ("Federal Decree by Law No. (33) of 2021 ... 7") leaked into chunks; a footer filter was added to `ingest.py` (confirm it was applied and all PDFs re-ingested).

## Test changes

Logged retrospectively on 2026-11-22 from the saved run files and file timestamps. Changes 1-6 were applied on 2026-11-19 before R3. Change 7 was applied on 2026-11-19 at 22:15, after R3 and before R4.

| # | Date | Test | Change | Reason |
|---|---|---|---|---|
| 1 | 2026-11-19 | all | `no_over_abstain` passes when the answer contains citations | A cited answer that starts with a caveat is not an abstention |
| 2 | 2026-11-19 | num-05 | Removed the commuting-time fact | Incidental to the question and mis-attributed (it is FDL 33/2021 Art. 17(3)) |
| 3 | 2026-11-19 | hol-02 | Relabelled as partial coverage: Islamic holidays follow the Hijri calendar, and the sources do not say when dates are announced | Expected facts came from the u.ae page, which is not in the corpus |
| 4 | 2026-11-19 | hol-03 | Moon-sighting fact replaced with "Islamic holidays are defined by Hijri dates"; Ramadan fact reworded to the 30th-day rule | Same; the resolution supports only the Hijri dates and the extra day |
| 5 | 2026-11-19 | abs-03 | Softened to "not covered by the legal sources" | Wording too specific; judge noisy |
| 6 | 2026-11-19 | fact-04 (first rewrite) | Sources set to FDL 13/2022 Art. 5-6 and CR 97/2022 Art. 10, 12 (were `todo`) | Corpus now contains the unemployment legislation |
| 7 | 2026-11-19 | fact-04, hol-01 | fact-04: one compound fact split into separate single facts (separate scheme, 12 months, 60%, 3 months, 30-day claim, coverage not determinable). hol-01: facts rewritten to the list of holidays, no confirmed Gregorian dates, and the Cabinet's power to move holidays | Compound facts made the judge grade several claims as one. **Made after both tests failed in `--only` runs**, so treat the R4 pass on these two as weaker evidence |

Open test issue (not yet changed): hol-01's third fact (the Cabinet may move holidays) is supported by CR 27/2024 **Art. 2**, but its sources list only Art. 1.

## Held-out set

2026-11-22: 12 questions drafted in `evals/heldout_questions.json` (ids `ho-01` to `ho-12`). Every required fact was checked against the ingested official text, and no retrieval or answer run has been done on them. Caveat: the drafter had seen the development results above, so the set is not fully blind. Run only for final reporting with `python evals/run_evals.py --file evals/heldout_questions.json`, and report development and held-out scores separately. Changes to held-out tests go in the Test changes table like any other test change.

| Run | Date | System | Overall | Retrieval recall | Cites expected article | No fake citations | Fact coverage | Notes |
|---|---|---|---|---|---|---|---|---|
| H1 | 2026-11-22 | Same as R4 (k=10, tool-call judge), first and only run of the frozen set | **11/12 (92%)** | 91% (10 items) | 100% | 100% | 96% (12 items) | `run-heldout_questions-20261122-213434`. Numeric 3/3, calculator used 2/2, abstentions 2/2. Only failure: ho-08 (see below) |

**H1 error analysis**

| Test | Failure | Layer | Cause |
|---|---|---|---|
| ho-08 (unemployment cap) | Missed the AED 20,000 cap for the second category | Retrieval | CR 97/2022 Art. 7 (category = subscription salary above AED 16,000) not in the top 10. The model saw both caps but not the category rule, and correctly said it could not tell which applies. FDL 13/2022 Art. 5 also not retrieved (recall 60%) |
| ho-08 | Missed the 30-day claim deadline | Generation (truncation) | CR 97/2022 Art. 9 was retrieved, but the answer is cut off mid-sentence ("starting from the date"). See the truncation finding below |
| ho-08 | `numeric_match` passed | Scoring | False positive: 20,000 appeared only as one of two caps, not as the answer |
| ho-03 | Passed with recall 50% | (none) | Art. 67 (30-day month) not retrieved; the calculator applies it anyway |

**Truncation finding (2026-11-22, found while analysing H1):** 13 saved answers across all runs end mid-sentence, including fact-04 and hol-01 in almost every development run (R2a, R2b, R3, R4 and the `--only` runs). The likely cause is `max_tokens=1000` in `app/answer.py`. Not confirmed, because `stop_reason` is not saved in the run files. Consequence: some fact-04 and hol-01 failures that led to test change 7 were probably caused by truncation, not by the tests. The H1 score stands as reported. Any held-out run after a fix is no longer blind and must be labelled that way.

## Next experiments

1. ~~Fix the judge parser and apply the test changes~~ (done before R3/R4).
2. R5: `TOP_K=5` on the current tests and judge, for a clean k comparison against R4.
3. Check where FDL 33/2021 Art. 6 ranks for the visa question, to confirm the fix is robust and not borderline.
4. Held-out set, then hybrid (keyword + embedding) retrieval and query rewriting if recall problems remain.
5. Compare one other embedding model on the same tests.