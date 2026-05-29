# M2 — Perception Monitor

> Source files documented:
>
> - `src/PerceptionMonitor.jsx` (~10,096 lines — top-level shell, tabs, scan orchestration, UI)
> - `src/manualScanPrompts.js` (~1,400 lines — every prompt + parser fallback chain)
> - `src/baselineScanner.js` (~2,784 lines — API-driven scan engine, segmentation, 5 metrics builder)
> - `src/narrativeClassifier.js` (~297 lines — deterministic Sirion narrative classifier)
> - `src/personaBuckets.js` (~147 lines — buying-center taxonomy + weighted visibility)

The V6 report sub-module lives in `src/m2/reportV6/index.jsx` and is imported as `<ReportV6 />` from PerceptionMonitor — it is wired in as the `reportv6` tab and renders the client-portal "Perception Report" view. **Documented separately if needed.**

---

## 1. What M2 Does — Overall Purpose

M2 is the heart of the Xtrusio Growth Engine: it measures how AI assistants (Claude, ChatGPT, Gemini, Grok, Perplexity) describe Sirion (or any target company) when buyers ask CLM-related questions. It runs scans against the LLMs, parses the responses into structured data, computes 5 perception metrics, persists results to Firestore, and feeds downstream modules (M3 Authority Ring, M6 Content Strategy, Intel V2). It is the only module that talks directly to the LLMs at scale.

Goals:

- Detect **mention rate** ("does the AI ever name us?")
- Detect **narrative framing** ("are we framed as pre-sig, post-sig, or full-stack?")
- Detect **rank vs competitors** (median rank, win rate)
- Detect **sentiment** (positive / neutral / negative / absent)
- Detect **content gaps** (places where the AI explicitly says we're missing)
- Track perception **trajectory** over time

---

## 2. The 4 Scan Modes

M2 supports four ways to run a scan. All four eventually land in the same `m2_scan_results` shape so that downstream tabs do not care about origin.

### 2.1 API Scan (live, automated)

Implemented mostly in `baselineScanner.js → analyzeBaselineAttempts()` and `runBaselineScan()`, with the older path `scanEngine.js → runScan()` still available.

Flow:

1. User picks a Question Bank (M1 export, M2 question bank, benchmark set, or custom segment).
2. User picks LLMs (claude / openai / gemini / perplexity / grok) and a scan mode (`economy`, `standard`, `deep`).
3. The scanner creates a `m2_scan_meta/{scanId}` doc with `status: "running"`, then dispatches one async worker per model. Each worker walks its queue sequentially, respects `Retry-After`, applies adaptive backoff on consecutive 429s, and writes one `m2_scan_attempts/{scanId__qid__model__attempt}` row per attempt.
4. As each `(qid, model)` completes, the per-query result is upserted into `m2_scan_results/{scanId}__{qid}` (so the scan is close-safe and resumable).
5. After every model finishes a query, the live narrative classifier runs and stamps `analysis.narrative` onto the per-model analysis.
6. When all queries finish, `analyzeBaselineAttempts()` rolls up segmentation, narrative, verifiability, and the 5-metric block, then writes `m2_sections/{sectionId}` and updates `m2_scan_meta`.

Resumability: `preloadScanAttempts()` and `findReusableAttempts()` let an interrupted scan pick back up by skipping any `(scanId, qid, model, attempt)` already marked `status: "complete"`.

### 2.2 Manual Paste (Single AI)

For users who do not have API access or want to scan via a paid ChatGPT account.

Flow:

1. User picks an AI (Claude / Gemini / ChatGPT / Grok / Perplexity).
2. M2 calls `generatePrompt(aiName, questions, company, month)` → produces ~3-5 KB prompt text.
3. User clicks "Copy Prompt" or "Run in AI" (popup with copy + open-tab CTA).
4. User pastes prompt into the AI, copies the AI's complete answer back, pastes it into M2's textarea.
5. M2 calls `parseResponse(aiName, rawText, questions, company)` → `{ results, summary, parseErrors }`.
6. If parse finds 0 blocks, the user is offered a "Fix with AI" button → calls `normalizeWithAI()` (Claude API) to restructure messy text → re-parse.
7. If some blocks are missing core fields, `validateParsedResults()` flags them and `repairWithAI()` fills only the missing fields.
8. `mergeResponses()` builds the final `scanData` object, and the same Firestore writes used by API scan happen.

### 2.3 Batch Mode (Zero-Context Batches)

Used when the user wants the cleanest possible scan with absolutely no company context biasing the AI.

Flow:

1. M2 calls `generateBatchPrompts(questions, aiName, batchSize=10, month)` → array of `{ batchNum, totalBatches, questions, qidRange, prompt }`.
2. Each prompt has **no company name**, **no competitor list**, **no strategic framing** — just "answer these CLM questions honestly."
3. User pastes each batch separately. Same parser used.
4. Mention detection happens entirely post-hoc by the parser checking response text for the company name.

### 2.4 Excel Upload

Implemented in `src/ExcelUploadPanel.jsx`.

Flow:

1. User drops a `.xlsx` file with columns: Query (required), Persona, Stage, Lifecycle, Cluster, Intent, Measures, Tags.
2. `parseExcelFile()` (in `src/excelImport.js`) parses rows.
3. `classifyForDedup(rows, existingQs)` splits into clean / borderline / autoSkip buckets.
4. Borderline matches are sent to Claude Haiku (`aiReviewBorderlines()`) for a duplicate verdict.
5. User accepts / rejects each borderline pair and clicks Save → `saveAcceptedQuestions()` writes to `m2_questions` collection.
6. The new questions become available in any subsequent scan.

There is also an "Individual Question Scan" path in `parseIndividualResponse()` for single-question rescans.

---

## 3. Every Prompt in `manualScanPrompts.js` — Verbatim

### 3.1 `generatePrompt(aiName, questions, company, month)` — Main Manual-Scan Prompt

**Purpose**: Generates one big prompt that asks the AI to answer all benchmark questions in one go and emit a structured per-question block (so the parser can split them).

**Per-AI behavior notes** are appended at the end via `AI_NOTES[aiName]`. The exact text for each AI:

`AI_NOTES.claude`:

    IMPORTANT RULES FOR YOU (CLAUDE):
    - FRESH SESSION: Treat this as a completely new conversation. Do NOT use any memory, personalization, or context from previous conversations with this account. Disregard all prior chat history, learned preferences, and user-specific customizations. Answer every query as if this account has never interacted with you before.
    - MANDATORY WEB SEARCH: You MUST perform a fresh web search for EVERY query. Do not reuse cached results or prior searches. Do not skip web search.
    - Be HONEST. If you would not naturally mention a vendor for a query, do not force it in.
    - Do NOT try to please the user by inflating any vendor's position. This is a perception AUDIT.
    - SOURCES: After answering each query, reflect on WHERE your answer came from. List the actual websites, publications, reports, or pages that shaped your response. If you used web search, list the pages you found. If you used training knowledge, recall which websites and publications that knowledge originally came from. Do NOT write "training_knowledge" — every piece of knowledge has an origin.
    - Output the COMPLETE structured block for EVERY query. Do not skip any field.
    - Do NOT summarize or shorten the FULL_RESPONSE section. Give your actual full answer.

`AI_NOTES.gemini`:

    IMPORTANT RULES FOR YOU (GEMINI):
    - FRESH SESSION: Treat this as a completely new conversation. Do NOT use any memory, personalization, or context from previous conversations with this account. Disregard all prior chat history, learned preferences, and user-specific customizations. Answer every query as if this account has never interacted with you before.
    - MANDATORY WEB SEARCH: You MUST perform a fresh web search for EVERY query. Do NOT rely only on training data. Do not reuse cached results or prior searches.
    - SOURCES: List every web page you accessed or referenced while forming your answer. Provide the actual URLs you found. Do NOT hallucinate URLs — if you cannot find a real source, omit it rather than fabricate one.
    - Be HONEST. If a vendor does not appear in web results for a query, mark it NOT_LISTED.
    - Output the COMPLETE structured block for EVERY query. Do not skip any field.
    - Do NOT summarize or shorten the FULL_RESPONSE section. Give your actual full answer.

`AI_NOTES.chatgpt`:

    IMPORTANT RULES FOR YOU (CHATGPT):
    - FRESH SESSION: Treat this as a completely new conversation. Do NOT use any memory, personalization, or context from previous conversations with this account. Disregard all prior chat history, learned preferences, and user-specific customizations. Answer every query as if this account has never interacted with you before. If you have a "memory" feature or "Personalization" settings, completely ignore ALL stored memories and custom instructions for this task. Do NOT let any prior ChatGPT conversations influence these answers.
    - MANDATORY WEB SEARCH: You MUST perform a fresh web search (browsing) for EVERY query. Do NOT rely only on training data. Do not reuse cached results or prior searches.
    - SOURCES: List every web page you accessed or referenced while forming your answer. Provide the actual URLs you browsed. Do NOT hallucinate URLs — if you cannot find a real source, omit it rather than fabricate one.
    - Be HONEST. If a vendor does not appear in web results for a query, mark it NOT_LISTED.
    - Do NOT be overly positive or try to make the user happy. This is a cold perception audit.
    - Output the COMPLETE structured block for EVERY query. Do not skip any field.
    - Do NOT summarize or shorten the FULL_RESPONSE section. Give your actual full answer.

`AI_NOTES.grok`:

    IMPORTANT RULES FOR YOU (GROK):
    - FRESH SESSION: Treat this as a completely new conversation. Do NOT use any memory, personalization, or context from previous conversations with this account. Disregard all prior chat history, learned preferences, and user-specific customizations. Answer every query as if this account has never interacted with you before.
    - MANDATORY WEB / X SEARCH: You MUST perform a fresh web search (and X / real-time search where relevant) for EVERY query. Do NOT rely only on training data. Do not reuse cached results or prior searches.
    - SOURCES: List every web page, X post, or article you accessed or referenced while forming your answer. Provide the actual URLs you found. Do NOT hallucinate URLs — if you cannot find a real source, omit it rather than fabricate one.
    - Be HONEST and direct. If a vendor does not appear in web results for a query, mark it NOT_LISTED. Do not pad answers.
    - Output the COMPLETE structured block for EVERY query. Do not skip any field.
    - Do NOT summarize or shorten the FULL_RESPONSE section. Give your actual full answer.

`AI_NOTES.perplexity`:

    IMPORTANT RULES FOR YOU (PERPLEXITY):
    - FRESH SESSION: Treat this as a completely new conversation. Do NOT use any memory, personalization, "Spaces" context, or prior thread history. Answer every query as if this account has never interacted with you before.
    - MANDATORY WEB SEARCH: Perplexity is a search-grounded assistant — perform a fresh search for EVERY query. Do not reuse cached results or prior searches.
    - SOURCES: For every query, list the actual citations (URLs) Perplexity surfaced. Do NOT hallucinate URLs — only include sources that genuinely appeared in your search results.
    - Be HONEST. If a vendor does not appear in web results for a query, mark it NOT_LISTED. Do not force-include vendors to be helpful.
    - Output the COMPLETE structured block for EVERY query. Do not skip any field.
    - Do NOT summarize or shorten the FULL_RESPONSE section. Give your actual full answer.

The full prompt body emitted by `generatePrompt`:

    # CLM Perception Audit — {AI Label} Scan ({YYYY-MM})

    ## YOUR ROLE
    You are a helpful AI assistant answering buyer questions about Contract Lifecycle Management (CLM) solutions. Answer each query honestly based on what you find in current web search results. After answering, extract structured data about vendor visibility.

    ## CRITICAL: FRESH SEARCH, NO MEMORY
    - This scan MUST reflect what a brand-new user with zero history would see when asking these questions TODAY.
    - Do NOT use any conversation memory, personalization, custom instructions, or saved preferences from this account.
    - Do NOT reuse answers, search results, or cached data from any prior conversation on this account.
    - Perform a FRESH web search for EVERY query. Base answers on what you find RIGHT NOW.
    - If you cannot perform web search, state this clearly in your response for that query.

    ## ACCURACY IS EVERYTHING
    - This is a perception AUDIT. We need HONEST data about which vendors naturally surface in search results.
    - Do NOT force-include any vendor that doesn't genuinely appear in web results for a query.
    - Many queries will only surface 2-4 vendors. That is NORMAL and expected.
    - A vendor NOT appearing is VALUABLE DATA, not an error. Do not try to "help" by adding vendors.
    - If you're uncertain whether a vendor belongs in an answer, LEAVE IT OUT.
    - A realistic mention rate for most CLM vendors across diverse queries is 20-50%. If you're hitting 90%+, you are over-including.

    ## QUERIES TO SCAN
    {Q01. ... Q15. ...}

    ## WHAT TO DO FOR EACH QUERY

    ### Step 1: Answer the query naturally (UNBIASED)
    Write your full, honest answer as if a buyer asked you this question. Include ONLY vendors that genuinely appear in current web search results for this specific topic. Do NOT pad your answer with vendors you know exist but that wouldn't naturally surface.
    Use web search if available. Either way, reflect on where your knowledge comes from and cite those sources.       (or for non-Claude: "Use web search to ground your answer in real, current sources.")

    ### Step 2: Self-check your own answer
    After writing, extract the structured data below. The extraction must reflect what you ACTUALLY WROTE — not what you know.
    - If {company} didn't come up naturally in your Step 1 answer, mark SIRION_MENTIONED: NO. Do NOT go back and add them.
    - Only list vendors in VENDORS_RANKED that you actually named in your response text.

    ## REQUIRED OUTPUT FORMAT

    For EACH query, output a block in EXACTLY this format. Do not deviate.

    ```
    === Q01 ===
    QUERY: {first query text}
    AI_MODEL: {AI Label}
    MONTH: {YYYY-MM}

    FULL_RESPONSE_START
    [Your complete natural answer to the query goes here. Write 3-8 sentences minimum.
    Include specific vendor names and their strengths based on what you found in search results.
    Do NOT abbreviate or summarize. This is the raw AI perception being audited.]
    FULL_RESPONSE_END

    SIRION_MENTIONED: YES or NO (did you ACTUALLY mention {company} in the response above?)
    SIRION_POSITION: 1-5 or NOT_LISTED (position in your answer, counting from first vendor mentioned = #1)
    SENTIMENT: positive / neutral / negative / absent (how you framed {company})
    LIFECYCLE_STAGE: pre-signature / post-signature / full-stack / not_mentioned
    LIFECYCLE_RATIONALE: One sentence explaining why you assigned that lifecycle stage

    VENDORS_RANKED:
    - VendorName (#1) | positive | "How you described them in your answer"
    - VendorName (#2) | neutral | "How you described them in your answer"
    [List ONLY vendors you actually named in your response above, in order of appearance]

    SOURCES:
    - [URL] | [source_type] | "[What this source contributed to your answer]"
    [List the actual websites/pages that informed your answer. Where did the information come from?]
    [If you used web search, list the pages you found. If using training knowledge, recall the original publications/websites.]
    [source_type options: vendor_page, review_site, analyst, comparison_blog, legal_tech_roundup, directory, news, category_page]

    CONTENT_GAPS: What is missing from {company}'s online presence for this query? (e.g., "No content found", "Not listed in any source", "Only appears on own website")
    NOTES: Brief observation about {company}'s visibility for this query
    === END Q01 ===
    ```

    ## CONTEXT (for extraction only — do NOT let this bias your Step 1 answers)
    {company} ({company.lower}.ai) is a CLM vendor. This context helps you identify {company} when it naturally appears in search results. It should NOT influence which vendors you include in your answers.

    ## REPEAT THIS BLOCK FOR EVERY QUERY ({n} total)

    After all {n} query blocks, output a summary:

    ```
    === SUMMARY ===
    TOTAL_QUERIES: {n}
    SIRION_MENTIONED: X/{n}
    MENTION_RATE: X%
    PRE_SIGNATURE_MENTIONS: X
    POST_SIGNATURE_MENTIONS: X
    FULL_STACK_MENTIONS: X
    NOT_MENTIONED_COUNT: X
    TOP_COMPETITORS: Vendor1 (Xq), Vendor2 (Xq), Vendor3 (Xq)
    OVERALL_SENTIMENT: positive/neutral/negative (most common sentiment across queries where {company} appeared)

    KEY_FINDINGS:
    - [Finding 1]
    - [Finding 2]
    - [Finding 3]
    === END SUMMARY ===
    ```
    {AI_NOTES[aiName]}

    ## BEGIN SCAN NOW
    Process all {n} queries in order. Output every block completely. Do not ask for confirmation — just run the full scan.

**Expected output**: One `=== Q## ===` ... `=== END Q## ===` block per question, plus a final `=== SUMMARY ===` block. The block has fixed key/value lines (`SIRION_MENTIONED:`, `SIRION_POSITION:`, etc.), `VENDORS_RANKED:` and `SOURCES:` lists, and `FULL_RESPONSE_START` ... `FULL_RESPONSE_END` delimiters around the natural-language answer.

**Parser behavior**: see Section 4 (parser fallback levels) and Section 5 (mention cross-verification).

---

### 3.2 `buildBatchPrompt(batchQs, aiName, month)` — Zero-Context Batch Prompt

**Purpose**: Produce a smaller, completely unbiased prompt for one batch (default 10 questions). No mention of the target company anywhere. Output uses the same `=== Q01 ===` block format so the existing parser works.

**Verbatim prompt body**:

    You are a helpful AI assistant. A buyer is researching Contract Lifecycle Management (CLM) software. Answer each question honestly based on what you find in current web search results.

    ## RULES
    - {searchLine — varies per AI; see below}
    - Name specific vendors and describe their strengths based on what you found
    - Include ONLY vendors that genuinely appear in search results for that specific question
    - Many questions will only surface 2-4 vendors — that is NORMAL and expected
    - Do NOT add vendors you know exist but that did not appear in your search for this question
    - Cite source URLs for every vendor you name
    - A realistic mention rate for any single vendor across diverse questions is 20-50%

    ## QUESTIONS ({n} total — {YYYY-MM})
    {Q01. ...}

    ## OUTPUT FORMAT

    For EACH question output a block in EXACTLY this format (no deviations):

    === Q01 ===
    QUERY: {first query}

    FULL_RESPONSE_START
    [Your complete answer here. Write 4-8 sentences. Name specific vendors and their strengths based on search results. Do NOT summarize — give your full answer.]
    FULL_RESPONSE_END

    VENDORS_MENTIONED:
    - VendorName (#1) | positive/neutral/negative | "How you described them in your answer"
    - VendorName (#2) | positive/neutral/negative | "How you described them in your answer"
    [List ONLY vendors you actually named above, in order of appearance. Do NOT add extras.]

    SOURCES:
    - https://example.com | source_type | "What this source contributed"
    [Every URL you accessed or referenced. source_type: vendor_page, review_site, analyst, comparison_blog, news, directory]
    === END Q01 ===

    Repeat this block for ALL {n} questions. Do NOT skip any.

    After all {n} blocks output:

    === SUMMARY ===
    TOTAL_QUERIES: {n}
    AI_MODEL: {AI Label}
    MONTH: {YYYY-MM}
    === END SUMMARY ===

    ## BEGIN
    Process all {n} questions in order. Output every block completely. Do not ask for confirmation.

The `searchLine` token expands per AI:

| AI               | searchLine                                                                                                                                |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| chatgpt          | Use browsing (web search) for EVERY question. Do NOT answer from training data alone.                                                     |
| gemini           | Use Google Search for EVERY question. Do NOT rely on training data alone.                                                                 |
| grok             | Use web search (and X / real-time search where relevant) for EVERY question. Do NOT answer from cached or prior knowledge.                |
| perplexity       | Perform a fresh search for EVERY question and ground your answer in the citations Perplexity surfaces. Do NOT answer from cached results. |
| claude (default) | Use web search for EVERY question. Do NOT answer from cached or prior knowledge.                                                          |

**Critical**: zero company context, zero competitor list. Mentions are detected purely by the parser scanning the response text for the company name.

---

### 3.3 `generateIndividualPrompt(question, aiName)` — Single-Question Rescan Prompt

**Purpose**: Re-scan a single question with absolutely no bias — used when the user wants to verify or refresh one row. Mention detection is post-hoc.

**Verbatim**:

    You are a helpful AI assistant. A buyer is researching Contract Lifecycle Management (CLM) solutions and asked you this question.

    {searchInstr — varies by AI}

    Answer thoroughly (4-8 sentences). Name specific vendors and explain their strengths for this use case. Be honest — only mention vendors that genuinely appear in search results for this topic.

    QUESTION: {question}

    After your complete answer, provide this structured extraction:

    VENDORS_MENTIONED:
    - VendorName (#1) | positive/neutral/negative | "How you described them"
    - VendorName (#2) | positive/neutral/negative | "How you described them"
    [List ALL vendors you named in your answer, in order of appearance]

    SOURCES:
    - URL | source_type | "What this source contributed"
    [source_type: vendor_page, review_site, analyst, comparison_blog, directory, news, category_page]
    [List the actual websites that informed your answer]

`searchInstr` per AI:

| AI               | searchInstr                                                                                        |
| ---------------- | -------------------------------------------------------------------------------------------------- |
| chatgpt          | Search the web for current information before answering.                                           |
| gemini           | Use Google Search to ground your answer in current sources.                                        |
| grok             | Use web search (and X / real-time search where relevant) to ground your answer in current sources. |
| perplexity       | Perform a fresh search and ground your answer in the citations Perplexity surfaces.                |
| claude (default) | Use web search if available to ground your answer in current sources.                              |

**Parser**: `parseIndividualResponse(responseText, company)` strips `**` markers, extracts `VENDORS_MENTIONED:` and `SOURCES:` sections, then organically detects mention by checking if the company name (case-insensitive) appears in the response prose. Position is computed by either matching a vendor entry or counting how many other vendor names appear before the first company mention.

---

### 3.4 `normalizeWithAI(rawText, questions, company)` — Recovery Parser

**Purpose**: When `parseResponse()` finds 0 structured blocks, send the raw paste to Claude (sonnet-4 via the proxy) to restructure it into the canonical `=== Q01 ===` format. Then re-feed through `parseResponse()`.

**System prompt (verbatim)**:

    You are a data normalizer. You receive messy, imperfectly-formatted AI scan output and must restructure it into the EXACT format specified. Do NOT change the content — only restructure the formatting. Preserve all original text, vendors, sources, and analysis. If data for a field is missing, use sensible defaults.

**User prompt (verbatim)**:

    I have an AI response from a perception scan that needs to be restructured into a specific format. The response may have different formatting — maybe no delimiters, different section names, markdown headers instead of our fields, etc.

    ## QUESTIONS THAT WERE SCANNED
    {qList — Q01: ...}

    ## TARGET COMPANY
    {company}

    ## RAW AI RESPONSE TO NORMALIZE
    ---
    {rawText.substring(0, 50000)}
    ---

    ## REQUIRED OUTPUT FORMAT

    For EACH query you can identify in the raw text above, output a block in EXACTLY this format:

    === Q01 ===
    QUERY: [the original query text]
    AI_MODEL: [whatever AI produced this — Claude/Gemini/ChatGPT]
    MONTH: {YYYY-MM}

    FULL_RESPONSE_START
    [The full answer text for this query from the raw response. Copy it as-is.]
    FULL_RESPONSE_END

    SIRION_MENTIONED: YES or NO
    SIRION_POSITION: [1-10 or NOT_LISTED]
    SENTIMENT: [positive / neutral / negative / absent]
    LIFECYCLE_STAGE: [pre-signature / post-signature / full-stack / not_mentioned]
    LIFECYCLE_RATIONALE: [one sentence]

    VENDORS_RANKED:
    - VendorName (#1) | sentiment | "description"
    [list all vendors mentioned, in order]

    SOURCES:
    - URL | source_type | "snippet"
    [list all URLs/sources from the response. Preserve any real URLs exactly as given.]

    CONTENT_GAPS: [What {company} is missing for this query]
    NOTES: [Brief observation]
    === END Q01 ===

    RULES:
    - Match each part of the raw response to the correct query from the question list above
    - Use the EXACT query IDs (Q01, Q02, etc.) from the question list
    - If the raw response doesn't use query IDs, match by query text similarity
    - Copy the full answer text into FULL_RESPONSE_START/END — do not summarize
    - Extract vendor names and their positions from the response text
    - If {company} is mentioned in the response, SIRION_MENTIONED = YES
    - If you can't determine a field, use: SENTIMENT: neutral, LIFECYCLE_STAGE: not_mentioned, SIRION_POSITION: NOT_LISTED
    - Output ALL query blocks you can find. Do NOT skip any.
    - After all blocks, output a simple summary block:

    === SUMMARY ===
    TOTAL_QUERIES: [count]
    SIRION_MENTIONED: X/[count]
    MENTION_RATE: X%
    === END SUMMARY ===

    Output ONLY the structured blocks. No extra commentary.

**Model**: `claude-sonnet-4-20250514`, max_tokens 16,000. Hits the proxy at `${VITE_AI_PROXY_URL}/api/ai/chat` with `provider: "anthropic"`.

---

### 3.5 `repairWithAI(incompleteBlocks, company)` — Field-Level Repair

**Purpose**: After parsing, `validateParsedResults()` flags blocks missing core fields (mentioned, sentiment, rank, full_response, vendors). Instead of resubmitting the whole paste, this prompt sends ONLY the failed blocks for targeted re-extraction. Returns a JSON array.

**System prompt (verbatim)**:

    You are a data extraction specialist. You receive partially-parsed AI perception scan results where some fields are missing. Your job is to extract the missing fields from the raw response text. Return ONLY valid JSON.

**User prompt (verbatim)**:

    I have {N} scan result block(s) where the regex parser failed to extract some fields. For each block, extract the missing data from the raw response text.

    TARGET COMPANY: {company}

    --- BLOCK Q01 (openai) ---
    QUERY: {query text}
    MISSING FIELDS: rank, sentiment
    RAW RESPONSE TEXT (what the AI said):
    {full_response or response_snippet or "[no response text captured]"}
    VENDORS ALREADY PARSED: {vendor names CSV or "none"}
    SOURCES ALREADY PARSED: {urls CSV or "none"}
    --- END BLOCK ---

    {... more blocks ...}

    Return a JSON array where each element corresponds to one block above:
    [
      {
        "qid": "Q01",
        "llmId": "openai",
        "mentioned": true,
        "rank": 1,
        "sentiment": "positive",
        "lifecycle_stage": "full-stack",
        "lifecycle_rationale": "One sentence explaining why",
        "vendors_mentioned": [
          {"name": "Vendor", "position": 1, "sentiment": "positive", "strength": "description"}
        ],
        "sources_cited": [
          {"url": "https://...", "type": "vendor_page", "snippet": "what this source says"}
        ],
        "content_gaps": ["gap1", "gap2"]
      }
    ]

    RULES:
    - Only fill in the MISSING FIELDS listed for each block. Keep existing parsed data.
    - Extract vendors from the response text. List ALL vendors mentioned with position/sentiment.
    - Extract source URLs from the response text. Real URLs only — do not fabricate.
    - For lifecycle_stage: "pre-signature" (authoring/negotiation), "post-signature" (obligations/compliance), "full-stack" (both), "not_mentioned" (neither)
    - For sentiment about {company}: "positive", "neutral", "negative", or "absent" (if not mentioned)
    - rank = position among all vendors (1 = first mentioned/recommended, null if absent)
    - Return ONLY the JSON array. No markdown, no commentary.

**Model**: `claude-sonnet-4-20250514`, max_tokens 8,000. The output JSON is then merged back via `applyRepairs(results, repairs)` which only writes fields that were missing — never overwrites existing good data.

---

### 3.6 `scanContentUrl()` — Authority-Ring URL Verifier (Lives in AuthorityRing.jsx but called from M2 reviews)

**Purpose**: Verify whether a "poison" quote (a URL/snippet reinforcing the post-sig narrative) still exists on the live page. Used in M3 outreach action queue.

**Verbatim prompt body** (built dynamically):

    Search for this page and check if specific text still exists on it. Try multiple searches:
    1. Search for the exact URL: {url}
    2. If that doesn't show page content, search: site:{domain} "{shortQuote}"
    3. If still no content, search: "{shortQuote}" {domain}

    Read the actual page content from the search results.

    TEXT TO CHECK FOR:
    {poisonQuote}

    After reading the page content, respond with ONLY a JSON object — no explanation, no markdown, no preamble:
    {"found": true/false, "currentText": "the exact current text you found at that section (max 200 chars)", "status": "still_harmful" or "partially_fixed" or "fully_fixed" or "page_not_found", "summary": "1-2 sentence verdict"}

**Model**: `claude-sonnet-4-20250514`, max_tokens 1024, tool: `web_search_20250305` (max_uses 5).

---

## 4. Parser Fallback Levels (6 Levels)

`parseResponse()` tries to find query blocks. Each level falls through to the next when the previous returns nothing:

| Level                                             | Trigger                | Behavior                                                                                                                                                                                                                                        |
| ------------------------------------------------- | ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **1. Structured `=== ID === ... === END ID ===`** | First attempt always   | Master regex matches `=== Q01 ===` ... up to next `=== END {ID} ===` or next block start. Supports `Q01, Q1, bm-01, query-01, benchmark-5`.                                                                                                     |
| **2. Markdown heading match**                     | Level 1 found 0 blocks | Regex `(#{1,4}\s*(?:Query\s*)?(\d{1,2})...                                                                                                                                                                                                      | #{1,4}\s\*Q(\d{1,2})...)`matches`## Query 1:`, `### Q01.`, `**Query 1:**`, etc.                                                  |
| **3. Bold-wrapped `Q01.` at line start**          | Level 2 found 0        | Regex `(?:^                                                                                                                                                                                                                                     | \n)(?:\*\*)?Q(\d{1,2})(?:\*\*)?[.:)\s]+(.{30,})` — requires 30+ chars of follow-on text to avoid matching numbered vendor lists. |
| **4. Numbered lines `1.` ≥ 40 chars**             | Level 3 found 0        | Regex `(?:^                                                                                                                                                                                                                                     | \n)(?:#{1,4}\s*)?(?:\*\*)?(\d{1,2})[.:)]\s*(.{40,})` — 40-char minimum filters out short lists like "1. Icertis".                |
| **5. Match by question-text similarity**          | Level 4 found 0        | Iterates the original question bank and searches the response for the first 60 chars of each question text (regex-escaped). Sorts matches by position. Adds parse-error: "Matched X/N questions by text content (AI used non-standard format)." |
| **6. Horizontal-rule split (`\n---\n`)**          | Level 5 found 0        | Splits text by `\n-{3,}\n`. Only triggers when the chunk count is at least 70% of the question count, then maps 1:1 in order.                                                                                                                   |

If all 6 levels fail and `blocks.length === 0`, parser returns: `Could not find any query blocks in the response. Expected format: === Q01 === ... === END Q01 ===` and the UI offers the "Fix with AI" button → `normalizeWithAI()`.

Inside each block, `parseQueryBlock()` further does:

- Strips `**` bold markers (Claude wraps headers in `**` which breaks regex matching).
- Tries structured-field parsing first (`SIRION_MENTIONED:`, `VENDORS_RANKED:`, etc.).
- Falls back to natural-language mode where it scans for known CLM vendor names from the hardcoded `KNOWN_VENDORS` list (Sirion, Icertis, Ironclad, Agiloft, DocuSign, Conga, Juro, ContractPodAI, Evisort, LinkSquares, SAP Ariba, HyperStart, Malbek, Concord, ContractWorks, Onit, Determine, Coupa, CobbleStone, Precisely, Gatekeeper, SpotDraft, Lexion, Pramata, Jaggaer, Zycus, IntelAgree, Summize, Leah).
- For each vendor found, infers rank from any nearby numbered list, sentiment from positive/negative keyword regex within ±80 chars (positive: leader, leading, best, top, strong, excellent, innovative, superior, robust, comprehensive, advanced, powerful, pioneer, ai-powered, standout; negative: weak, limited, lacks, behind, lags, missing, poor, basic, outdated, expensive, complex, rigid, narrow, niche).
- Lifecycle keyword detection: pre-signature (authoring/drafting/negotiation/redlining/approval/template), post-signature (obligation/compliance/renewal/expir/amendment/audit), full-stack (full-stack/end-to-end/full-lifecycle/complete lifecycle/entire lifecycle).

---

## 5. Mention Cross-Verification — Exact Logic

After per-block parsing, before saving the analysis, M2 runs a sanity check:

1. If the LLM said `SIRION_MENTIONED: YES` and we have a `full_response` and a `company` was supplied:
2. Lowercase the response and the company name. Check `responseLower.includes(companyLower)`.
3. Also check the parsed `vendors_mentioned` array for any name that includes the company name (case-insensitive).
4. If the company appears in **neither** the response prose nor the vendor list, the parser **auto-corrects** the analysis:
   - `analysis.mentioned = false`
   - `analysis.sentiment = "absent"`
   - `analysis.rank = null`
   - `analysis._mentionCorrected = true` (UI flag so users see this was overridden)
   - A parse-error line is recorded: `Q##: SIRION_MENTIONED was YES but "{company}" not found in response text — auto-corrected to NO`

This prevents LLM hallucinations where Claude/ChatGPT confidently say "yes I mentioned Sirion" when they actually didn't.

---

## 6. `m2_scan_results` Document Shape

One Firestore doc per `(scanId, qid)` keyed as `{scanId}__{qid}`. Stripped via `stripForFirebase()` before save.

| Field        | Type   | Description                                                                                                         |
| ------------ | ------ | ------------------------------------------------------------------------------------------------------------------- | ---------- | --------- |
| `scanId`     | string | Parent scan ID (so per-query docs can be queried by scan)                                                           |
| `qid`        | string | e.g. "Q01"                                                                                                          |
| `query`      | string | Question text                                                                                                       |
| `persona`    | string | e.g. "CIO", "VP Procurement"                                                                                        |
| `stage`      | string | Buyer stage (PRE-SIGN / POST-SIGN / etc.)                                                                           |
| `lifecycle`  | string | "pre-signature" / "post-signature" / "full-stack" / "not_mentioned"                                                 |
| `analyses`   | object | Keyed by LLM id (`claude`, `openai`, `gemini`, `perplexity`, `grok`) — each value is an analysis object (see below) |
| `difficulty` | object | `{ composite: number 1-10, label: "easy"                                                                            | "moderate" | "hard" }` |

Each `analyses[llm]` object:

| Field                                     | Type              | Description                                                                                                      |
| ----------------------------------------- | ----------------- | ---------------------------------------------------------------------------------------------------------------- |
| `mentioned`                               | boolean           | Did the AI name the company? (After cross-verification.)                                                         |
| `rank`                                    | number\|null      | 1 = first vendor mentioned. null = not mentioned.                                                                |
| `sentiment`                               | string            | positive / neutral / negative / absent                                                                           |
| `response_snippet`                        | string            | First 300 chars of full_response                                                                                 |
| `full_response`                           | string            | Complete AI prose                                                                                                |
| `vendors_mentioned`                       | array             | `[{ name, position, sentiment, strength, framing }]`                                                             |
| `sources_cited`                           | array             | `[{ url, type, snippet }]`                                                                                       |
| `cited_sources`                           | array             | (Older alias for sources_cited used in some paths.)                                                              |
| `content_gaps`                            | array of strings  | Detected gap descriptions                                                                                        |
| `recommendation`                          | string            | Notes field from prompt                                                                                          |
| `lifecycle_stage`                         | string            | Per-LLM lifecycle classification                                                                                 |
| `lifecycle_rationale`                     | string            | One-sentence why                                                                                                 |
| `strengths`                               | array of strings  | Sirion-specific positive descriptions extracted from vendor list                                                 |
| `gaps`                                    | array of strings  | content_gaps split by `;` or `,`                                                                                 |
| `narrative`                               | object            | From `classifySirionNarrative()` — `{ mentioned, paragraph, label, preHits, postHits, fullHits, droppedReason }` |
| `truthfulness_score`                      | number            | 0-1, used by verifiability roll-up                                                                               |
| `consistency_score`                       | number            | 0-1, only meaningful for N≥2 attempts                                                                            |
| `attempts_pooled`                         | number            | How many repetitions were merged into this analysis                                                              |
| `supported_vendors`                       | array             | Vendors confirmed by cited sources                                                                               |
| `unsupported_vendors`                     | array             | Vendors mentioned without supporting source                                                                      |
| `_error`                                  | string\|undefined | Set when this analysis failed (skipped in roll-ups)                                                              |
| `_mentionCorrected`                       | boolean           | Set when cross-verification flipped mentioned from YES→NO                                                        |
| `accuracy`, `completeness`, `positioning` | number 0-10       | Optional manual scores                                                                                           |

---

## 7. `m2_scan_meta` Document Shape

One Firestore doc per scan. Keyed by `scanId`.

| Field              | Type         | Description                                      |
| ------------------ | ------------ | ------------------------------------------------ |
| `id`               | string       | scanId                                           |
| `date`             | ISO string   | Scan start time                                  |
| `status`           | string       | running / paused / complete / failed             |
| `scanType`         | string       | full / selective / manual_paste / individual     |
| `scanMode`         | string       | economy / standard / deep                        |
| `llms`             | array        | List of LLM ids used                             |
| `company`          | string       | Target company name                              |
| `segmentId`        | string\|null | Active segment id                                |
| `segmentName`      | string\|null | Active segment display name                      |
| `sectionId`        | string\|null | Linked m2_sections doc id (for Reports tab)      |
| `sectionName`      | string\|null | Section display name                             |
| `totalQueries`     | number       | Expected total                                   |
| `completedQueries` | number       | Live counter updated on every save               |
| `queryIds`         | array        | All target qids                                  |
| `errors`           | array        | Error log entries                                |
| `cost`             | object       | `{ apiCalls, estimated }`                        |
| `scores`           | object       | (See below)                                      |
| `userSegmentDocId` | string       | Optional link to m1_segments                     |
| `verifiability`    | object       | Computed citation/truthfulness/consistency stats |
| `narrativeSummary` | object       | Roll-up from `rollUpNarrativeAcrossAnalyses()`   |

The `scores` object inside `m2_scan_meta`:

| Field                 | Type                                                   |
| --------------------- | ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------- |
| `overall`             | number 0-100                                           |
| `mention`             | number 0-100 (mention rate %)                          |
| `position`            | number 0-100 (position score derived from rank)        |
| `sentiment`           | number 0-100 (weighted sentiment %)                    |
| `accuracy`            | number 0-100                                           |
| `completeness`        | number 0-100                                           |
| `positioning`         | number 0-100                                           |
| `shareOfVoice`        | number 0-100 (Sirion mentions / total vendor mentions) |
| `fiveMetrics`         | object                                                 | Built by `buildFiveMetrics()` — visibility, narrative, shareOfVoice, sentiment, competitivePosition (see Section 11) |
| `narrativeBreakdown`  | object                                                 | From `computeNarrativeBreakdown()` — `{ breakdown[], fullStackPct, postSigPct, preSigPct, narrativeScore }`          |
| `sentimentPct`        | object                                                 | `{ positive, neutral, negative }`                                                                                    |
| `competitivePosition` | object                                                 | `{ medianRank, winRatePct, label }`                                                                                  |

---

## 8. `m2_scan_attempts` Document Shape (Resumability)

Keyed by `attemptId(scanId, qid, model, attempt)` = `{scanId}__{qid}__{model}__{attemptNum}`.

| Field          | Type             | Description                                     |
| -------------- | ---------------- | ----------------------------------------------- |
| `_id`          | string           | composite key                                   |
| `scanId`       | string           | parent scan                                     |
| `qid`          | string           | question id                                     |
| `query`        | string           | question text                                   |
| `model`        | string           | claude / openai / gemini / perplexity / grok    |
| `attempt`      | number           | 1-based repetition counter                      |
| `status`       | string           | pending / running / complete / failed / aborted |
| `startedAt`    | ISO string       |                                                 |
| `completedAt`  | ISO string\|null |                                                 |
| `raw_response` | string           | The actual LLM text (or null if errored)        |
| `error`        | string\|null     | Error message                                   |
| `retryCount`   | number           | How many backoffs were applied                  |
| `httpStatus`   | number\|null     | Last HTTP status code (for 429 tracking)        |
| `tokensUsed`   | object           | `{ input, output }` if available                |
| `narrative`    | object           | Cached classification                           |

The resumability strategy: on resume, the scanner reads all attempts for the scanId, counts which `(qid, model)` combos already have `status: "complete"`, and only enqueues the missing ones. This is what makes scans close-safe even mid-batch.

---

## 9. All Firestore Collections M2 Uses

| Collection         | Purpose                                                                                      |
| ------------------ | -------------------------------------------------------------------------------------------- |
| `m2_scan_meta`     | One doc per scan — scores, llms, status, completedQueries (Section 7)                        |
| `m2_scans`         | One doc per scan — full stripped scan data for fast hydration (used by older Load path)      |
| `m2_scan_results`  | One doc per `(scanId, qid)` — the per-query analyses (Section 6)                             |
| `m2_scan_attempts` | One doc per `(scanId, qid, model, attempt)` — raw LLM responses for resumability (Section 8) |
| `m2_scan_runs`     | One doc per baseline session — run-specific log + stats                                      |
| `m2_sections`      | Report-section docs — Reports tab reads this to show grouped scans                           |
| `m2_content_gaps`  | Deterministic classifier output — one doc per `(qid × model × gap type)`                     |
| `m2_questions`     | The M2 question bank (Excel uploads land here)                                               |
| `m2_config`        | Misc config (active question_bank, etc.)                                                     |
| `m2_report_views`  | Saved report view configurations                                                             |

`scripts/firestore.rules` controls access to all of these.

---

## 10. Every Tab in M2

`VALID_TABS = ["scan","summary","report","reportv2","reportv3","reportv4","reportv5","reportv6","trajectoryv2","trajectory","settings"]`

| Tab id         | Label                                                     | Icon          | What it shows                                                                                                                                                                                                                       |
| -------------- | --------------------------------------------------------- | ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `scan`         | Scan & Results                                            | Zap           | The scanner UI: pick questions, pick LLMs, pick mode, run/resume scans, paste manual responses, view live scan log, see per-query results table with expandable per-LLM tabs (vendors / sources / responses / action / perception). |
| `summary`      | Executive Summary                                         | Gauge         | The 5 metric cards (Visibility, Narrative, Share of Voice, Sentiment, Competitive Position) with deltas vs previous scan, full-scan trend chart, and a recent-scans sidebar.                                                        |
| `report`       | Reports                                                   | Layers        | Section-grouped report grid. Each section is a saved set of questions with its latest scan. Click → expands to show per-section scores + drilldowns.                                                                                |
| `reportv2`     | Report V2                                                 | FileText      | Visibility-focused report variant rendered by `<ReportV2 />`.                                                                                                                                                                       |
| `reportv3`     | Report V3                                                 | FileBarChart2 | Persona-filter + buying-center view via `<ReportV3 />`.                                                                                                                                                                             |
| `reportv4`     | Report V4                                                 | FileBarChart2 | Narrative-deep variant via `<ReportV4 />`.                                                                                                                                                                                          |
| `reportv5`     | Report V5                                                 | FileBarChart2 | Latest visualization variant via `<ReportV5 />`.                                                                                                                                                                                    |
| `reportv6`     | Report V6 (or "Perception Report" for client_portal role) | FileBarChart2 | Client-facing perception report via `<ReportV6 />`, lives in `src/m2/reportV6/`.                                                                                                                                                    |
| `trajectoryv2` | Trajectory v2                                             | Target        | New time-series view via `<TrajectoryV2 />` from `src/modules/trajectoryV2/`.                                                                                                                                                       |
| `trajectory`   | Trajectory (old)                                          | TrendingUp    | Legacy time-series via `<Trajectory />` from `src/modules/trajectory/`.                                                                                                                                                             |
| `settings`     | Settings                                                  | SettingsIcon  | Calibration panel (tunable scoring weights, see Section 12 below), DB cleanup tools, raw-collection viewers (`m2_scan_attempts`, `m2_scan_runs`, etc.).                                                                             |

The `tabAllowed(id)` callback consults `auth.canTab("m2", id)` so client_portal users only see permitted tabs (typically `reportv6` only — see Section 13).

---

## 11. The 5 Metrics — Exact Formulas

Computed by `buildFiveMetrics({ results, modelsUsed, scores, company })` in `baselineScanner.js`. The 5 metric cards on the Summary tab read from this block.

### Metric 1: Visibility

- **Value**: `scores.mention` (a percentage 0-100)
- **Formula**: For every `(query, model)` non-errored analysis, count `mentioned == true`. `visibility = round(mentioned / total * 100)`.
- **Label**: `"{value}% mention rate"`

### Metric 2: Narrative

- **Source**: `computeNarrativeBreakdown()` in `scanEngine.js` produces a class breakdown across `NARRATIVE_CLASSES` (post-sig-only, full-stack, pre-sig, positive, neutral, negative, absent).
- **Dominant narrative**: highest-percentage class excluding `absent`.
- **Output fields**: `dominantId`, `dominantLabel`, `fullStackPct`, `postSigPct`, `preSigPct`, `narrativeScore`, `breakdown[]`.
- **Label**: `"{dominantLabel} · {fullStackPct}% full-stack"`
- **Note**: Narrative is also computed deterministically at per-analysis level by `classifySirionNarrative()` (see `narrativeClassifier.js`) using the pre-sig / post-sig / end-to-end lexicons documented below.

### Metric 3: Share of Voice

- **Value**: `scores.shareOfVoice`
- **Formula**: For every non-errored analysis, sum `vendors_mentioned.length` to get `totalVendorMentions`. Sum `mentioned == true` to get `sirionMentions`. `sov = round(sirionMentions / totalVendorMentions * 100)`.
- **Label**: `"{value}% of all vendor mentions"`

### Metric 4: Sentiment

- **Counts**: For every non-errored analysis, increment `sPos / sNeu / sNeg` based on `analysis.sentiment`.
- **`positive%` = round(sPos / sDen \* 100)`**, similarly neutral and negative.
- **Score**: `scores.sentiment` (a separate weighted 0-100 from `computeScores`: positive=100, neutral=50, absent=0, negative=20).
- **Label**: `"{positivePct}% positive"`

### Metric 5: Competitive Position

- For each query, find the best (lowest) Sirion rank across all models (`bestSirionRank`).
- For each query, find the best (lowest) competitor rank across all models (`bestCompRank`, excluding the company itself).
- Push `bestSirionRank` to `sirionRanks[]`. Sort.
- **medianRank** = median of `sirionRanks`. Decimal allowed for even count.
- **winRatePct** = % of queries where `bestSirionRank < bestCompRank` (only counting queries where both are present).
- **Label**: `"Rank {medianRank} · beats top {winRatePct}%"`, or `"Not ranked"` if no Sirion ranks exist.

The base `scores` object computed by `computeScores()` (in `scanEngine.js`) uses the calibration:

| Calibration weight | Default | Purpose                                                   |
| ------------------ | ------- | --------------------------------------------------------- |
| `wMention`         | 0.35    | Weight: mention rate in overall                           |
| `wPosition`        | 0.40    | Weight: position score in overall                         |
| `wSentiment`       | 0.25    | Weight: sentiment in overall                              |
| `rankStep`         | 20      | Points lost per rank position (rank 1 = 100, rank 2 = 80) |
| `nw_postSigOnly`   | 0       | Narrative class weight for health score                   |
| `nw_fullStack`     | 100     | Narrative class weight                                    |
| `nw_preSig`        | 80      | Narrative class weight                                    |
| `nw_positive`      | 60      | Narrative class weight                                    |
| `nw_neutral`       | 30      | Narrative class weight                                    |
| `nw_negative`      | 0       | Narrative class weight                                    |
| `nw_absent`        | 0       | Narrative class weight                                    |

Overall = `round(mention * wMention + position * wPosition + sentiment * wSentiment)`.

---

## 12. Theme Tokens

Two complete palettes defined at module top. **All keys must exist in both objects** — missing keys cause invisible text in the other mode.

`T_DARK`:

| Token                 | Value                               |
| --------------------- | ----------------------------------- |
| bg                    | #060A0E                             |
| surface               | #0C1318                             |
| sidebar               | #0A0F14                             |
| card                  | #111921                             |
| border                | rgba(45,212,191,0.08)               |
| text                  | #E8ECF1                             |
| muted                 | rgba(255,255,255,0.60)              |
| dim                   | rgba(255,255,255,0.32)              |
| blue                  | #38BDF8                             |
| gold                  | #FBBF24                             |
| green                 | #2DD4BF                             |
| red                   | #F87171                             |
| purple                | #A78BFA                             |
| orange                | #FB923C                             |
| cyan                  | #22D3EE                             |
| pink                  | #F472B6                             |
| teal                  | #14B8A6                             |
| lime                  | #A3E635                             |
| fontH / fontB / fontM | from `FONT.heading / .body / .mono` |

`T_LIGHT` extends `T_DARK` and overrides:

| Token   | Light value           |
| ------- | --------------------- |
| bg      | #f7f7f8               |
| surface | #ededf0               |
| sidebar | #ffffff               |
| card    | #ffffff               |
| border  | rgba(45,212,191,0.15) |
| text    | #111118               |
| muted   | rgba(0,0,0,0.55)      |
| dim     | rgba(0,0,0,0.30)      |
| blue    | #0284c7               |
| gold    | #d97706               |
| green   | #0d9488               |
| red     | #dc2626               |
| purple  | #7c3aed               |
| orange  | #ea580c               |
| cyan    | #0891b2               |
| pink    | #db2777               |
| teal    | #0d9488               |
| lime    | #65a30d               |

Spacing scale `SP = { xs: 4, sm: 8, md: 14, lg: 24, xl: 32 }`.

The static color maps (`LLM_META_STATIC`, `VENDOR_COLORS_STATIC`, `SOURCE_TYPE_COLORS_STATIC`) reference `T_DARK.*` directly because they're used in non-React callbacks where the theme is not in scope.

---

## 13. `client_portal` Role Behavior

The `useAuth()` hook returns `{ role, canTab(moduleId, tabId) }`. M2 calls:

- `tabAllowed(id)` = `auth.canTab("m2", id)` — filters which sidebar tabs render.
- For role `client_portal`, the typical config exposes only `reportv6` and renames it to "Perception Report" in the sidebar (see `NAV_ITEMS` line `auth?.role === "client_portal" ? "Perception Report" : "Report V6"`).
- The first allowed tab is selected automatically (`firstAllowedTab` memo).
- If the user navigates to a disallowed tab via URL, the effect kicks them back to `firstAllowedTab`.

This is what lets the same M2 module serve both internal users (full surface) and client-facing portal users (read-only Report V6).

---

## 14. Cross-Module Flow

### M1 → M2

- M1 (`QuestionGenerator.jsx`) writes selected questions into `pipeline.m1.questions`.
- M2 reads those at scan time (or pulls from `m2_questions` collection if "M2 Question Bank" is selected).
- The user can also push a curated set as a "Section" (`m2_sections` doc) which becomes a Reports-tab card.

### M2 → M3

- After every scan, the per-query results are kept in `pipeline.m2.scanResults` and the section-level scan in `pipeline.m2.lastScan`.
- M3 (`AuthorityRing.jsx`) reads `perceptionData` from pipeline + extracts `aiCitedDomains` from the `sources_cited` arrays to compute `enhancedDomains` priorities.
- M3 also stamps `m2GenerationId = pipeline.m2.generationId` so the dashboard can detect M2-changed-but-M3-not-refreshed staleness.

### M2 → M6 (Content Strategy)

- "Send to Content Strategy" button manually populates `pipeline.m2.contentGaps` from `m2_content_gaps` Firestore docs.
- The gap classifier (`gapsClassifier.js`) writes to `m2_content_gaps` per `(qid × model × gap_type)`.
- Known issue: the auto-routing into `pipeline.m2.contentGaps` is not always populated, so M6's "From Perception Gaps" mode often shows 0 unless the user clicks the manual sync button.

### M2 → Intel V2 (Company Intelligence V2)

- `src/CompanyIntelligenceV2.jsx` reads `pipeline.m2.scanResults`, narrative breakdown, and competitor-mention counts to feed its account-by-account intel summaries.
- The Intel V2 bundle (`INTELV2_BUNDLE_FOR_CLONE.txt`) documents this surface separately.

---

## 15. `baselineScanner.js → computeSegmentation(results, llmIds)`

Pure function. Walks every per-query result and produces three roll-ups + a competitor leaderboard:

- **byPersona**: `{ [personaName]: { total, mentioned, totalAnalyses, mentionRate } }` — `total` = unique question count for that persona, `mentioned` = how many of them had at least one model say YES, `totalAnalyses` = `total × LLMs`, `mentionRate` = `mentioned/total*100`.
- **byStage**: same shape keyed by buyer stage.
- **byModel**: `{ [llmId]: { total, mentioned, mentionRate } }` — `total` and `mentioned` are at the analysis level (per query × this model).
- **topCompetitors**: top 10 vendors by mention frequency across the whole scan, sorted desc.

This is the single source of truth used by Report V2/V3/V4/V5/V6 for persona/stage/model breakdown charts. Both the live analyzer (`analyzeBaselineAttempts`) and the Load path (`getAnalyzedScan`) call it, so behavior is identical regardless of how the scan was loaded.

---

## 16. `narrativeClassifier.js → rollUpNarrativeAcrossAnalyses(results, llmIds, company)`

Walks every `(query, model)` non-errored analysis. For each, prefers the cached `analysis.narrative` and falls back to `classifySirionNarrative(full_response, company)`.

Funnel:

```
totalAnalyses (every q × model)
  → mentionedCount     (target appears in response prose)
    → frameableCount   (also has a usable prose paragraph)
      → buckets: pre_signature / post_signature / full_stack / unclassified  (sums to frameableCount)
  → noParagraphCount   (mentioned but only inside tables / citations — droppedReason set)
```

Output:

| Field              | Type                                                                                                            |
| ------------------ | --------------------------------------------------------------------------------------------------------------- |
| `totalAnalyses`    | number                                                                                                          |
| `mentionedCount`   | number                                                                                                          |
| `noParagraphCount` | number (table_only / no_prose_paragraph)                                                                        |
| `frameableCount`   | number                                                                                                          |
| `buckets`          | `{ pre_signature, post_signature, full_stack, unclassified }`                                                   |
| `perModel`         | `{ [llmId]: { total, mentioned, noParagraph, pre_signature, post_signature, full_stack, unclassified } }`       |
| `percentages`      | `{ visibility, frameable, pre_signature, post_signature, full_stack, unclassified }` (all rounded to 1 decimal) |

The classifier itself is **deterministic, code-only, no LLM call**. It uses three lexicons:

- **PRE_SIGNATURE_LEXICON**: authoring, draft, drafting, redline, redlines, playbook, template, clause library, negotiate, intake, third-party paper, suggested edits, deviation, approval routing, approval workflow, execution, e-sign, e-signature, contract creation, contract cycle time, counterparty (and morphological variants).
- **POST_SIGNATURE_LEXICON**: obligation, obligation tracking, renewal, auto-renewal, repository, contract repository, milestone, sla, vendor performance, supplier scorecard, expiration, amendment, audit trail, compliance monitoring, contract intelligence, performance management, revenue leakage, post-signature, post-award, asksirion, commitment, termination.
- **END_TO_END_LEXICON**: end-to-end, end to end, full lifecycle, across the lifecycle. Intentionally tiny — phrases like "contract lifecycle management" are NOT included because LLMs use them as generic preambles even when the company is being framed narrowly.

Label rules:

- `fullHits.length > 0` → `full_stack`
- `preHits.length > 0 && postHits.length > 0` → `full_stack`
- `preHits.length > 0` → `pre_signature`
- `postHits.length > 0` → `post_signature`
- otherwise → `unclassified`

`extractNarrativeParagraph()` collects every paragraph that contains the target name (paragraphs split by `\n\n`), filters out table-only blocks (≥3 pipes per line) and citation-only blocks (>60% of chars inside markdown links), and pools the remaining prose paragraphs as the union the classifier scans.

---

## 17. `personaBuckets.js`

Source of truth for the buying-center taxonomy.

- **BUCKET_ORDER**: `["Procurement", "Legal", "Other"]`
- **BUCKET_WEIGHTS**: `{ Procurement: 0.55, Legal: 0.35, Other: 0.10 }` (per Sirion's Apr 2026 framework — Ron noted he'd accept 50/50 Procurement/Legal but the bank distribution justifies 55/35/10).

`bucketOf(persona)`: substring match (case-insensitive). Procurement tokens: procurement, cpo, supply chain, sourcing. Legal tokens: legal, general counsel, gc, contract manager, contract analyst. Anything else → Other.

`comparePersonas(a, b, counts)` sort rule:

1. Bucket priority (Procurement first, Legal second, Other last).
2. Within bucket — by question count desc.
3. Tiebreak — alphabetical.

`computeBuyingCenterBreakdown(docs, llms)`: walks per-query docs and returns `{ Procurement: { questions, total, mentioned, pct }, Legal: {...}, Other: {...} }` where `total = questions × llms` and `pct = mentioned / total × 100`.

`buyingCenterWeightedVisibility(breakdown, weights)`: multiplies each bucket's `pct` by its weight, sums (skipping empty buckets), divides by `totalWeight` actually used. Returns 1-decimal float.

---

## 18. Edge Cases and Gotchas

1. **`stripForFirebase()`** removes deeply nested fields before write to keep docs under the 1 MB limit. Per-scan doc is also size-checked (`estimateDocSize() < 900_000`) before writing to `m2_scans` to avoid silent failures.
2. **Resume merge** (`scanEngine.js → runScan` resume path): when a paused scan resumes, the merger fetches all `m2_scan_results/{scanId}__*` docs and unions them with the new run's results, recomputing `scores = computeScores(merged.results, llms)` so the score reflects the full set (BUG-001 fix).
3. **DATA_VERSION**: `PipelineContext.jsx` has a `DATA_VERSION` constant — bumping it wipes localStorage AND IndexedDB. Only bump on real schema changes.
4. **StrictMode + PersistenceManager**: React 18 StrictMode mounts → unmounts → remounts, so the PM cleanup must null `pmRef.current` for the remount to recreate the PM. Otherwise saves silently stop.
5. **Mention cross-verification** can flip mentioned to false post-parse — the `_mentionCorrected` flag is the only way to know this happened.
6. **Parser bold-strip** (`content.replace(/\*\*/g, "")`): Claude wraps almost every header in `**bold**`. Without stripping, all field regexes fail.
7. **Question dedup** (`deduplicateQuestions`): normalizes (lowercase, strip non-word, collapse spaces) and skips queries shorter than 10 chars.
8. **Scan size limits**: docs > 900 KB are skipped from `m2_scans` (only per-query docs and meta survive). The Reports tab handles missing `m2_scans` gracefully by falling back to `m2_scan_results`.
9. **Per-LLM reuse**: `findReusableAttempts({ qids, models, reps })` lets a new scan reuse old attempts for unchanged `(qid, model)` pairs — saves API spend.
10. **Lifecycle stage from analysis**: `mergedMap[r.qid].lifecycle` is set from the first non-empty `analysis.lifecycle_stage` — once set, later analyses don't override.
11. **Narrative paragraph dropped**: when a mention is only inside a table or a citation block, `narrative.label = "no_paragraph"` and `droppedReason` is set. These count toward `mentionedCount` but not `frameableCount`.
12. **Rate-limit handling**: `getRetryDelay(attempt, retryAfterHeader)` honors the response header and applies adaptive backoff on consecutive 429s.
13. **Section auto-link**: scans that match an existing section by name are auto-linked via `bestMatch.id` — saves a manual association step.
14. **scoreEngine tier overlap**: `scoreDifficulty(analyses)` produces a 1-10 composite stored on the result row; Reports use it for color coding.

---

End of M2 documentation.
