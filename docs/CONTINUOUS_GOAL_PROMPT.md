# Continuous Quality & Security Goal Prompt

Copy the prompt below and run it with `/goal` to start the continuous enforcement loop.
The loop checks all invariants below on med.debkay.com (dev) and iterates until three
consecutive all-green runs, then idles for 6 hours before re-checking.

**Stop the loop:** type `stop /goal`

---

```
/goal Continuously enforce the following invariants on the dev deployment
(med.debkay.com) until ALL of them pass green for three consecutive runs:

  1. Every answer returned by POST /api/v1/query has at least one citation
     OR the structured no_evidence error (error_code=="no_evidence") —
     never ungrounded "Expert opinion" as the entire answer.
  2. Every reference URL resolves (HTTP 200) and points to an allowed domain
     (pubmed.ncbi.nlm.nih.gov, ncbi.nlm.nih.gov, medlineplus.gov,
     accessdata.fda.gov, dailymed.nlm.nih.gov, nice.org.uk,
     semanticscholar.org, doi.org, clinicaltrials.gov).
  3. scripts/run_all_tests.sh exits 0.
  4. /cso (security audit) reports no Critical or High findings;
     all secrets remain in .env files; no hardcoded keys in git history.
  5. /benchmark p95 page load < 3 s on the answer route.
  6. Adversarial fixtures (prompt injection, sycophancy bait, nonsense
     queries) all produce safe, balanced, or no_evidence outputs.
  7. langgraph executes all three nodes (fetch, vector, semantic_cache)
     on every query — verified via X-Test-Mode: 1 debug block.
  8. Scalability check: scripts/run_quality_tests.py run with --parallel 20
     completes with zero 5xx and p95 latency < 15 s.

On each iteration:
  - Run scripts/run_all_tests.sh
  - Run /cso daily mode
  - Run /benchmark
  - Run /qa-only standard tier on med.debkay.com
  - Summarise PASS/FAIL per invariant
  - If any FAIL: investigate root cause (/investigate), propose a fix as a
    plan file, ask the user to approve before implementing, then commit to
    dev and rebuild dev containers only.
  - If all PASS: idle for 6 hours, then re-run (medical sources update;
    citation health drifts).

Never push to main. Never rebuild prod containers. Never disable a test
to make it pass. Never bypass /careful warnings. Stop the loop only when
the user types "stop /goal".
```
