# Phase A — TYPED vs FETCH-ALL (retrieval metrics)

| Query | Cond | lat(s) | esearch | total | uniq | dup× | capKept | capWaste | empty | tier |
|---|---|--:|--:|--:|--:|--:|--:|--:|:-:|:--|
| drug: empagliflozin MoA | typed | 3.79 | 4 | 2 | 2 | 1.0 | 2 | 0 | · | unknown |
| drug: empagliflozin MoA | fetch_all | 9.03 | 25 | 24 | 6 | 4.0 | 16 | 8 | · | guideline |
| disease: CKD staging | typed | 3.28 | 4 | 15 | 10 | 1.5 | 1 | 14 | · | unknown |
| disease: CKD staging | fetch_all | 8.43 | 31 | 36 | 16 | 2.25 | 16 | 20 | · | guideline |
| symptom-only: fatigue+night sweats | typed | 2.77 | 4 | 13 | 7 | 1.86 | 2 | 11 | · | unknown |
| symptom-only: fatigue+night sweats | fetch_all | 11.2 | 41 | 39 | 11 | 3.55 | 27 | 12 | · | guideline |
| evidence: SGLT2i in HF | typed | 2.41 | 4 | 8 | 5 | 1.6 | 3 | 5 | · | unknown |
| evidence: SGLT2i in HF | fetch_all | 16.74 | 43 | 54 | 18 | 3.0 | 32 | 22 | · | guideline |
| procedure: CVC insertion | typed | 3.48 | 5 | 1 | 1 | 1.0 | 0 | 1 | · | unknown |
| procedure: CVC insertion | fetch_all | 5.87 | 25 | 29 | 8 | 3.62 | 17 | 12 | · | guideline |
| comparative: warfarin vs apixaban | typed | 8.61 | 12 | 7 | 2 | 3.5 | 7 | 0 | · | unknown |
| comparative: warfarin vs apixaban | fetch_all | 12.63 | 41 | 37 | 11 | 3.36 | 32 | 5 | · | guideline |
| complex: DOC for CKD+T2DM+HF | typed | 3.91 | 12 | 16 | 1 | 16.0 | 16 | 0 | · | guideline |
| complex: DOC for CKD+T2DM+HF | fetch_all | 10.79 | 43 | 37 | 6 | 6.17 | 31 | 6 | · | guideline |
| complex: metformin in CKD+HF | typed | 3.72 | 12 | 15 | 0 | 0.0 | 15 | 0 | Y | guideline |
| complex: metformin in CKD+HF | fetch_all | 12.03 | 43 | 57 | 24 | 2.38 | 21 | 36 | · | guideline |
| drug-in-disease: amiodarone in AF | typed | 4.13 | 4 | 8 | 4 | 2.0 | 2 | 6 | · | unknown |
| drug-in-disease: amiodarone in AF | fetch_all | 13.53 | 41 | 63 | 25 | 2.52 | 26 | 37 | · | guideline |
| non-medical: capital of France | typed | 2.89 | 4 | 5 | 0 | 0.0 | 5 | 0 | Y | unknown |
| non-medical: capital of France | fetch_all | 5.59 | 25 | 20 | 0 | 0.0 | 20 | 0 | Y | guideline |
