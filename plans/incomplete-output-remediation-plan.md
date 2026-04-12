# Incomplete Output Remediation Plan

## Why The Current Output Is Thin

Based on the current backend, the incomplete answers are caused by a few compounding issues:

1. DSPy is allowed to emit explicit insufficient-data placeholders
   - In [backend/app/services/dspy_signatures.py](/root/projects/med-ai-project/backend/app/services/dspy_signatures.py), `MedicalResponseGeneration` explicitly tells the model to return `"Insufficient data from available sources for this section."` whenever fetched data is missing for a section.
   - It also forbids using model knowledge outside fetched data, so thin retrieval becomes thin output.

2. DSPy still runs even when retrieval is weak or empty
   - In [backend/app/services/rag_pipeline.py](/root/projects/med-ai-project/backend/app/services/rag_pipeline.py), the DSPy path runs whenever a user key exists, even if `fetched_data` is sparse.
   - There is no retrieval sufficiency gate before the adaptive generator is called.

3. The data passed into DSPy is aggressively compressed
   - `_summarize_fetched()` in [backend/app/services/rag_pipeline.py](/root/projects/med-ai-project/backend/app/services/rag_pipeline.py) truncates source fields hard and only includes a small number of abstracts.
   - So even when retrieval succeeds, DSPy often sees a reduced snapshot rather than the full evidence.

4. Retrieval can fall back too early
   - `fetch_data_for_query()` in [backend/app/services/data_fetcher.py](/root/projects/med-ai-project/backend/app/services/data_fetcher.py) marks `fallback_to_llm=True` quickly when entity extraction or fetch success is weak.
   - General queries, weak entity extraction, or partial fetches can push the system into a thin path too early.

5. API fetch timeouts are tight for multi-source medical retrieval
   - The current fetch timeout budget is short, so broad PubMed/NCBI retrieval can return partial results or none.

6. Sparse-response repair is only applied to the standard pipeline, not the DSPy path
   - `_is_critically_sparse()` and the expansion retry live in the standard JSON pipeline in [backend/app/services/rag_pipeline.py](/root/projects/med-ai-project/backend/app/services/rag_pipeline.py).
   - The DSPy response can return early without any equivalent sparse retry or retrieval retry loop.

7. The current adaptive loop is single-pass
   - The system analyzes once, fetches once, and generates once.
   - There is no second retrieval pass like: "these sections are still weak, fetch more evidence specifically for them."

## Fix Plan

### Step 1. Add retrieval sufficiency scoring before generation

Build a deterministic sufficiency scorer in the backend that evaluates:
- number of sources retrieved
- number of non-empty source fields
- number of guideline/review/trial abstracts
- whether section-critical fields exist

Rules:
- if retrieval is strong enough, run DSPy generation
- if retrieval is weak, do not generate yet
- instead trigger a second retrieval pass

This removes the current behavior where DSPy is asked to write a complete answer from obviously incomplete evidence.

### Step 2. Add a second-pass targeted retrieval loop

After initial DSPy analysis, use:
- `query_type`
- `entities`
- `condition_context`
- `required_sections`
- `response_focus`

to run targeted follow-up searches.

Examples:
- if dosing is missing, run dosing-specific drug queries
- if comparative safety is missing, run comparative safety/effectiveness PubMed searches
- if disease management is thin, run management/guideline/consensus searches
- if evidence output is thin, run broader trial/review/guideline searches using the analyzed focus rather than the raw user text only

Goal:
- retrieval becomes iterative instead of one-shot

### Step 3. Expand what DSPy actually sees

Replace the current `_summarize_fetched()` truncation strategy with a richer structured context pack:
- include more abstracts
- include more source metadata
- include stronger section labels
- include condition-management evidence for drug-in-disease queries
- preserve the best evidence first instead of arbitrary truncation

This should be token-budgeted, but not starved.

### Step 4. Apply sparse detection and repair to DSPy outputs too

Add a DSPy-specific sparse validator after adaptive generation:
- detect too-few sections
- detect repeated insufficient-data placeholders
- detect section titles with almost no substantive items
- detect missing references or missing key clinical fields

If sparse:
- do not return immediately
- run targeted retrieval expansion
- rerun DSPy generation once with the enriched evidence pack

Right now this protection exists mainly for the standard pipeline, not the adaptive one.

### Step 5. Improve fetch success semantics

Refactor `fetch_success` so it is not a binary "got enough or not" switch based on a narrow subset of fields.

Instead:
- track partial success by source
- track field-level coverage
- track evidence depth by query type

This avoids cases where retrieval is treated as successful but still too thin for a useful answer, and also avoids giving up too early when some evidence exists but needs expansion.

### Step 6. Broaden retrieval for general and poorly-structured queries

General queries currently risk weak retrieval because they may not map cleanly to the structured fetch path.

Fix:
- add DSPy-to-search-query expansion for broad clinical questions
- derive 2-5 search formulations from the analyzed focus
- run broad PubMed/NCBI retrieval on those expansions
- merge and deduplicate results before generation

This is especially important for "approach to", "management of", "workup of", and broad clinical summary queries.

### Step 7. Increase retrieval budget where it matters

Increase:
- API fetch timeout budget
- per-query abstract caps
- evidence summary budget for adaptive mode

Do this selectively:
- disease
- comparative
- evidence
- drug-in-condition

Do not waste budget on short straightforward drug label lookups.

### Step 8. Replace the generic insufficient-data UX with specific deficiency reporting

If evidence is genuinely incomplete, the system should say exactly what is missing:
- "FDA label found, but no dosing data for this condition"
- "Guidelines found, but no head-to-head comparison studies"
- "Only review-level evidence found; no RCTs identified"

That makes the output clinically usable even when incomplete.

### Step 9. Add query-level observability

For every query, log:
- analyzed query type
- extracted entities
- sources hit
- fetch counts
- sufficiency score
- whether second-pass retrieval ran
- whether sparse retry triggered
- why the final response was marked thin

Without this, fixing the issue will stay trial-and-error.

### Step 10. Add regression tests with real failure cases

Build a test set of queries that currently return incomplete answers and lock in expected improvements.

Test buckets:
- Indian brand name to generic/salt
- drug in disease context
- disease management
- comparative therapy
- evidence/safety in special populations
- broad "approach to" queries

Each test should assert:
- minimum section coverage
- minimum reference count
- no repeated insufficient-data placeholders unless truly unavoidable

## Implementation Order

1. Add observability and retrieval sufficiency scoring
2. Add DSPy sparse validation and stop returning thin adaptive responses immediately
3. Add second-pass targeted retrieval
4. Expand `_summarize_fetched()` into a richer evidence pack
5. Broaden general-query retrieval and improve query expansion
6. Tune timeouts, budgets, and per-type thresholds
7. Add regression tests and golden queries

## Expected Outcome

After this change, the backend should:
- stop returning incomplete adaptive answers just because the first retrieval pass was thin
- fetch again when needed instead of giving up
- give fuller section coverage for disease/comparative/evidence queries
- only use an explicit insufficient-data notice when the system has already tried retrieval expansion and still cannot find enough evidence
