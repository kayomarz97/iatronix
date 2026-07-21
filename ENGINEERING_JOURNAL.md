# Iatronix — Engineering Journal & Lessons Learnt

> The narrative behind the build: why each design choice was made, the bugs that
> taught us, and the provider-agnostic refactor of June 2026. Source of truth for
> the public "Lessons Learnt" article (rendered at `/lessons`).

---

## 1. What Iatronix is

A **BYOK (bring-your-own-key) medical reference engine**. Users supply their own
LLM API key; the system classifies a clinical query, fetches live evidence from
10+ free medical APIs (PubMed/NCBI, openFDA, RxNorm, DailyMed, MedlinePlus, NICE,
ClinicalTrials.gov, Semantic Scholar, NCBI Bookshelf, ChEMBL), ranks it by
evidence quality, and synthesises a **typed, evidence-graded** answer where every
clinical claim traces to a fetched source. No server-side LLM keys, ever.

The hardest engineering problem here is not generation — it is **grounding**:
making a language model say only what the retrieved evidence supports, with a
correct citation, and nothing else.

---

## 2. The two seams every regression came from

Mining 100+ commits, almost every production bug traced to one of two seams:

### Seam A — citation grounding under a changing pipeline
References kept *disappearing*. It was fixed at least five times (`ec0a4d9` →
`ef8fdeb` → `0043476` → `e634961` → `fd8345d` → `53f8957`) before it stuck. The
lesson: **grounding must be deterministic, not best-effort.** The solution that
finally held was a chain of deterministic mechanisms:

1. **`[REF_N]` citation tokens** — the LLM may only cite tokens we injected into
   the data block; a post-processing resolver maps them to real PMIDs/URLs. The
   model can't invent a citation because it can only emit a token we defined.
2. **Article Registry** — an immutable post-fetch registry where every entry has
   a *validated article-level URL* (entries without a resolvable URL are
   excluded). The final reference list is built from this, not from LLM output.
3. **Demote, don't drop** — ungrounded claims are demoted to low-confidence
   "Expert opinion", never deleted. Drop-based logic was exactly what made whole
   reference lists vanish mid-stream.
4. **Evidence Floor** — no synthesis without ≥1 citable source; if retrieval is
   genuinely empty, the system returns an honest "No evidence found" rather than
   an ungrounded answer. This closed the last bypass (`f9abb3f`).

A subtle, expensive one: **per-section vs response-level references.** Enforcing
"≥1 reference per section" later caused the answer to visibly *shrink* when the
final `done` event arrived. The fix (`dd907dd`): references live at the response
level, and the UI never shrinks vs. what the user already saw streaming.

### Seam B — provider/model selection state
The provider toggle kept getting *stuck* (`344832e`, `806153e`, `fd8345d`). Root
cause: the backend used "first key wins" instead of honouring the user's
`engine_pref`, and the frontend held a stale closure of the model config at
submit time. The fix: a **server-canonical `active_provider`** + `engine_pref`
priority, and the frontend re-fetches config at submit. The lesson that drove the
whole June refactor: **provider/model identity must have exactly one source of
truth**, or the FE and BE will drift.

---

## 3. Hard-won gotchas (the ones that trip the next engineer)

- **`gpt-oss-*` must route to Cerebras *before* the `gpt-` OpenAI check.** Order
  is load-bearing; otherwise `gpt-oss-120b` 404s on OpenAI.
- **Cerebras prompt caching is byte-fragile.** It's a server-side *prefix*
  auto-cache: a single character change before the static prefix silently kills
  the hit. The static system text must be a constant, leading, and never
  interpolated. (And on Cerebras, cache hits are *not* cheaper — they only cut
  latency, and only on `gpt-oss-120b`.)
- **Anthropic Haiku 4.5's cache floor is 4,096 tokens, not ~1k.** Marking a
  smaller block with `cache_control` does nothing (no error, no cache). Gate
  cache breakpoints on the real per-model token floor.
- **`anthropic-beta` cache header is retired** — 1-hour TTL is just
  `cache_control:{type:ephemeral, ttl:"1h"}` now.
- **`text-embedding-004` was shut down (Jan 2026)** and `claude-sonnet-4-20250514`
  retires June 15 2026 — APIs drift; verify model IDs against live docs, never
  memory.
- **Stance-loaded queries bias retrieval.** "Why is X *not* rational?" fetches
  one-sided evidence. The Stance Neutralizer strips valence to a neutral clinical
  question *before* retrieval, so the model doesn't mirror the user's framing.

---

## 4. The provider-agnostic refactor (June 2026)

Seam B forced the issue: four overlapping, drifting catalogs defined providers
and models (`config.py` role fields with a *second, wrong* pricing table;
`model_registry.py`; `schemas/models.AVAILABLE_MODELS`; the frontend's hardcoded
fallbacks). Provider identity was imperative — `provider == "anthropic"` branched
in a dozen files. Adding a provider meant editing many files and praying the FE
and BE agreed.

**The fix: one file.** `backend/config/providers.yaml` is now the single source
of truth. A loaded registry drives routing, client construction, caching,
pricing, the `/api/v1/providers` endpoint, and the frontend's key-entry UI +
model picker. The five hand-tuned `"/"` model-fallback heuristics collapsed into
one registry-ownership rule. The provider→DB-column map, the auth allowlist, and
the circuit-breaker set all derive from the registry. Flipping a provider's
`enabled` flag activates it on **both** the frontend and backend with no other
edit — which is exactly the FE/BE drift that Seam B kept producing, designed out.

Two more things came with it:
- **Storage-agnostic keys.** A `KeyStore` abstraction puts BYOK keys behind
  `get/set/clear`, with Postgres authoritative and an optional server-side
  Firestore mirror (dual-write). Switching the primary is a config flip — no
  backfill — which makes migration safe.
- **Deep-grounded answers.** The old "thin retrieval → quick degrade" path was
  replaced by **bounded parallel citation-chasing**: from any found article,
  follow its forward/backward citations (depth ≤5, ~120s budget, branches in
  parallel), assemble a grounded answer, or — rarely, honestly — say "No evidence
  found." It never fabricates to avoid that terminal.

**Method that paid off:** before writing a line of adapter or graph code, we
fetched the *current* official docs for every provider and LangGraph and wrote
them down (`INTEGRATION_NOTES.md`). That caught the embedding-model shutdown, the
Sonnet retirement, the wrong pricing in two places, the Haiku cache floor, and
the LangGraph `recursion_limit` default change — all things memory got wrong.

---

## 5. Principles, distilled

1. **Grounding is deterministic or it's broken.** Tokens → registry → demote →
   floor. Never trust the model to cite.
2. **One source of truth, or the layers drift.** Providers/models in one file;
   keys behind one abstraction; references at one level.
3. **Fail closed, honestly.** For a medical tool, "No evidence found" is a
   correct answer; a confident ungrounded answer is a bug.
4. **Read the current docs, not your memory.** APIs drift faster than intuition.
5. **Preserve the load-bearing invariants** (cache prefixes, timeouts, the
   evidence contract) when refactoring — change structure, not semantics.

## 6. Retrieval precision & output bounds (July 2026)

A run of production bugs this month all came from the same blind spot: *what happens when a query
fetches too much, or the wrong thing.*

1. **A size budget is not a count cap.** The reference list emitted every fetched article as a
   citation with no count limit. One broad query pulled ~4,000 unique articles and the answer tried
   to cite all 4,000 — a ~512 KB payload that broke JSON parsing (`Unterminated string`). The internal
   abstract cap only measured *characters*, so title-only articles (0 chars) bypassed it entirely.
   Fix: cap the citation list by *count* — keep every cited source, cap retrieved-but-unused at 40.
   Bound user-facing lists by count, independent of any internal char/size budget.
2. **Relevance needs a floor, not just a ranking.** "Does paracetamol cause fever" surfaced an
   unrelated post-op arthroplasty *fever* guideline — it matched the symptom, scored high on
   study-type/recency, and nothing dropped it, because the ranker only *reorders*. Fix (chosen by a
   2³ factorial, Haiku-judged): a relevance floor that drops entity-absent articles + adverse-sense
   query framing that fetches the *cause* sense instead of the *indication* sense. Together they cut
   off-topic 95%→75% and tripled the relevant articles kept. Quality can smuggle an off-topic source
   into an answer; you need a floor that *acts* on relevance, not just ranks by it.
3. **A feature can be live and do nothing.** A retrieval fallback merged, tests green, "live" — and
   never fired, because it sat behind an early-return whose bar was so low the guarded path almost
   never ran. Test that a feature *triggers* on its target case, not just that its helper works.
4. **Measure noisy external systems more than once.** Live PubMed shifts run-to-run; a single
   before/after once showed a phantom "rescue" that was network noise — gone on the median of three
   runs. Sample before trusting a delta.
5. **Retrieval breadth is a dial, not a maximum.** Widening the net (raising a threshold) pulled in
   mostly-irrelevant articles and hurt answer quality; a tighter setting was better. Precision/recall
   is a trade-off to tune, not a number to maximise.

## 7. Classifier robustness & the model-selection seam, again (July 2026)

Two user-reported symptoms — "the classifier routes wrong things" and "I picked Haiku but it ran
Cerebras" — turned out to be three separate bugs. Untangling them was the lesson.

1. **The error message named the wrong culprit.** "CKD hypertension which drugs to use" failed with
   `'DrugFetchResult' object has no attribute 'drug_name'`, so it *looked* like a misrouted `drug`
   query. It wasn't — the query classified correctly as `complex`, then crashed in the complex
   generation branch on a field that never existed (`DrugFetchResult` has `generic_name`/`brand_name`,
   not `drug_name`). Every other reader used a safe `getattr`; this one line used bare attribute
   access, so it only blew up when a complex query happened to populate `drug_data`. **Read the
   traceback's *location*, not its *noun* — the word "drug" in the error was a red herring.**

2. **Seam B reappears: the model picker was decoupled from the engine.** Selecting "Haiku" sent
   `model_id=claude-haiku…`, but `process_query()` chose the provider purely from `engine_pref` +
   which BYOK key existed — it never read the selected model. It grabbed the Cerebras key, and the
   Cerebras adapter's `resolve_model()` defensively swapped Haiku for `gpt-oss-120b`, so the answer
   *honestly* reported Cerebras. **The label was right; the routing threw the choice away.** Fix:
   when the model is explicit, the provider is derived from the model and its key is tried first —
   and if that key is missing we fail honestly instead of silently substituting. The UI now only
   offers engines you hold a key for, so the mismatch can't be created in the first place.

3. **Robustness ≠ a bigger model — it's deterministic backstops.** The classifier is one LLM call
   whose worst failure mode was silent: any malformed JSON collapsed to the expensive `complex`
   default with no signal. The fixes were all deterministic and cheap: tiered JSON recovery, Pydantic
   coercion of the type/confidence (code-side, **not** provider-specific tool-use — the classifier
   runs on Cerebras as often as Anthropic), and an entity-count tie-breaker for the genuinely
   ambiguous `evidence`-vs-`complex` boundary (≥2 named conditions ⇒ complex). The LLM keeps
   waffling on comorbidity questions; "count the conditions" is an objective signal it can't argue
   with.

4. **A new env var doesn't load on a single-service `--build`.** Enabling a flag in `.env.dev` and
   running `docker compose up -d --build <service>` brought the container up *without* the new var —
   it reused the old container's resolved environment. `--force-recreate` fixed it. Verify a
   flag-gated feature is actually flagged-on in the running container (`docker exec … printenv`)
   before concluding it "doesn't work."
