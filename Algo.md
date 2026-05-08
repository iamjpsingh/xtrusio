Here's the full list from earlier — all 10 battle-tested algorithms for analysis work, with library + use case.

---

## 1. Aho-Corasick — Multi-pattern string matching

| | |
|---|---|
| **What** | Scans text once and finds ALL keyword matches simultaneously |
| **Complexity** | O(n + m + k) — linear regardless of vocabulary size |
| **Library** | `pyahocorasick` |
| **Use** | Find all vendor mentions ("Sirion", "Icertis", "DocuSign", etc.) in one pass |
| **Beats** | Looping `.find()` per name — that's O(n × m) and crawls |

---

## 2. Damerau-Levenshtein — Fuzzy string matching

| | |
|---|---|
| **What** | Edit distance between two strings (handles insertions, deletions, substitutions, transpositions) |
| **Library** | `rapidfuzz` (C++ backed, drop-in replacement for fuzzywuzzy, 10× faster) |
| **Use** | Normalize variants — "Sirion Labs" / "SirionLabs" / "Sirion's" / "Syrion" → canonical "sirion" |
| **Beats** | Hand-rolled regex variants — `rapidfuzz` handles edge cases you'd miss |

---

## 3. Tokenization + n-grams + TF-IDF — Paragraph classification

| | |
|---|---|
| **What** | Split text into tokens, count n-gram occurrences, weight by inverse document frequency |
| **Library** | `spaCy` for tokenization, `scikit-learn`'s `TfidfVectorizer` |
| **Use** | Lifecycle stage classifier (END-TO-END / PRE / POST) — keyword-based with smart weighting |
| **Why TF-IDF** | A "lifecycle" hit in a paragraph dense with legal terms counts more than one in a noise-filled paragraph |

---

## 4. Set similarity — Jaccard + MinHash + LSH

| | |
|---|---|
| **What** | Measure overlap between two sets of words/shingles. MinHash + Locality-Sensitive Hashing finds near-duplicates in O(n) instead of O(n²) |
| **Library** | `datasketch` (battle-tested at Google, Spotify) |
| **Use** | "Did the LLM give us the same answer this time?" Compare 462 cells across multiple scans efficiently |
| **Beats** | Byte-equality (too brittle) or O(n²) pairwise comparison (too slow at scale) |

---

## 5. Embedding cosine similarity — Semantic similarity

| | |
|---|---|
| **What** | Embed text with a model, compute cosine distance — measures meaning, not just word overlap |
| **Library** | `sentence-transformers` (`all-MiniLM-L6-v2` is small/fast) or OpenAI `text-embedding-3-small` |
| **Use** | "Q002 Gemini in Scan #3 vs Scan #5 are 0.94 cosine similar — same answer, different wording" |
| **Tradeoff** | More accurate than MinHash for paraphrasing, but more expensive |

---

## 6. Reservoir sampling — Streaming random sample

| | |
|---|---|
| **What** | Pick K random items from a stream of unknown length in one pass with O(1) memory |
| **Library** | ~5 lines of Python (no library needed) |
| **Use** | "Spot-check 100 random cells from a 10,000-cell scan to confirm Sirion is still mentioned correctly" |
| **Beats** | Loading everything into memory just to `random.sample()` |

---

## 7. SHA-256 content-addressed cache — Deduplication

| | |
|---|---|
| **What** | Hash the request inputs (model + prompt + temperature + tools) → use that as cache key |
| **Library** | `hashlib` (Python stdlib) |
| **Use** | Skip duplicate LLM API calls automatically. Same as Git, npm, every CDN, every blob store |
| **Beats** | Multi-field equality checks (the bug class that caused "Full scan re-ran 57% of cells") |

---

## 8. Wilson score interval — Confidence intervals

| | |
|---|---|
| **What** | Mathematically correct CI on a binomial proportion. Used by every A/B testing platform (Optimizely, Statsig) |
| **Library** | `statsmodels.stats.proportion.proportion_confint` (one line) |
| **Use** | Tell clients "Sirion's mention rate is 47.3% ±3pp" with statistical rigor — defensible numbers |
| **Beats** | Hand-waved "looks like ~50%" or naive normal-approximation CI (breaks at low N) |

---

## 9. PageRank / HITS — Graph algorithms for citation networks

| | |
|---|---|
| **What** | Rank nodes (URLs/domains) in a graph by authority. Same algorithm Google has used for 25 years. |
| **Library** | `networkx` (a few lines) |
| **Use** | "Which sources are LLMs citing most when discussing CLM?" — domain-authority analysis |
| **When** | Not urgent for verify, useful for citation/source-of-truth analytics later |

---

## 10. Myers diff — Sequence alignment

| | |
|---|---|
| **What** | The diff algorithm Git uses — shows exactly what changed between two sequences |
| **Library** | `difflib` (Python stdlib) |
| **Use** | "Q002 Gemini was reused but had these 3 word changes" — for verify reports |
| **Beats** | Visual eyeballing or hand-rolled comparison |

---

## Quick reference matrix

| Algorithm | Library | Use case | Status |
|---|---|---|---|
| Aho-Corasick | `pyahocorasick` | Find all vendor mentions in prose | ✅ Day 1 |
| Damerau-Levenshtein | `rapidfuzz` | Normalize vendor name variants | ✅ Day 1 |
| TF-IDF + n-grams | `spaCy` + `scikit-learn` | Lifecycle stage classifier | ✅ Day 1 |
| Jaccard / MinHash + LSH | `datasketch` | Cross-scan duplicate detection | ✅ When comparing scans |
| Cosine similarity | `sentence-transformers` | Semantic same-answer detection | ✅ When MinHash isn't enough |
| Reservoir sampling | stdlib | Random sample from huge scans | When scaling to 10k+ |
| SHA-256 content cache | `hashlib` | Skip duplicate LLM calls | ✅ Day 1 — fixes major bug class |
| Wilson score CI | `statsmodels` | Defensible confidence intervals | ✅ Day 1 — required for client reports |
| PageRank / HITS | `networkx` | Citation graph analysis | Later — analytics feature |
| Myers diff | `difflib` (stdlib) | Diff "reused" responses | When debugging cache hits |

---

## Two principles that matter more than any algorithm

1. **Use battle-tested libraries, not hand-rolled code.** Every algorithm above has a Python library written by someone who spent years on edge cases. `rapidfuzz` is faster than anything you'd write. `datasketch` handles corner cases you wouldn't think of.

2. **Pick algorithms that are explainable to a client.** "We used Aho-Corasick to scan for vendor mentions" is defensible in an audit. "We used a deep learning embedding to vibe-check" is not, even if more accurate. **Audit credibility = every number traceable to a deterministic rule.**

---

## Day-1 minimum (for your verify/scoring pipeline)

Three algorithms get you 80% of what a serious perception-audit pipeline needs:

```
pyahocorasick    →  vendor mention detection
rapidfuzz        →  vendor name normalization
statsmodels      →  Wilson confidence intervals
```

Add the rest as you scale to multi-scan comparisons, semantic similarity, and citation analysis.