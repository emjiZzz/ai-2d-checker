---
title: Self-Learning AI Engine & 4 Pillars
type: engine-architecture
tags: [self-learning, active-learning, 4-pillars, hitl, vault-sync, few-shot]
---

# 🧠 Self-Learning AI Engine — The 4 Pillars

The Self-Learning AI Engine converts human engineer corrections (dismissals, category overrides, annotations) into an active learning feedback loop that continuously refines both deterministic RAG filters and Gemini LLM prompts.

```mermaid
flowchart TD
    User["🖥️ Desktop Review Workspace"] -->|Dismiss / Override| API["POST /api/v1/audits/feedback"]
    API -->|Save Event| DB[("MongoDB AuditFeedbackDocument")]
    
    DB -->|Few-Shot Exemplars| FewShot["FewShotRetriever (few_shot_retriever.py)"]
    FewShot -->|Inject Client Rules| Prompt["Gemini LLM System Instruction"]
    
    DB -->|Count Dismissals >= 3| AutoDoc["AutoDocEngine (auto_doc.py)"]
    AutoDoc -->|Auto-Write Markdown| Vault["Obsidian Second Brain (docs/vault)"]
    Vault -->|Live Sync (Pillar 1)| RAG["safe_filter in orchestrator.py"]
```

---

## 🏛️ The 4 Pillars

### 1. Pillar 1: Live Obsidian Vault-to-Runtime Sync
- **File**: [`services/backend/infrastructure/knowledge/vault_sync.py`](file:///d:/RAYSAN/ai-2d-checker/services/backend/infrastructure/knowledge/vault_sync.py)
- **Role**: Reads Markdown notes from `docs/vault/08 - Client Domain & CAD Rules/` at runtime.
- **Function**: Extracts dynamic tolerance keywords (`指示外公差`, `仕上精度`, `機械加工`), surface roughness regex patterns (`\b\d+(\.\d+)?S\s*~`), and metadata anchors. Connects to `safe_filter()` in [`orchestrator.py`](file:///d:/RAYSAN/ai-2d-checker/services/backend/infrastructure/audit/comparison/orchestrator.py).

### 2. Pillar 2: Human Feedback Persistence API
- **Model**: [`services/backend/domain/models/audit_feedback.py`](file:///d:/RAYSAN/ai-2d-checker/services/backend/domain/models/audit_feedback.py) (`AuditFeedbackDocument`)
- **API Endpoint**: `POST /api/v1/audits/feedback` in [`audits.py`](file:///d:/RAYSAN/ai-2d-checker/services/backend/api/routers/audits.py)
- **Role**: Records human engineer overrides (`dismissed`, `confirmed_valid`, `category_override`) triggered from the desktop review workspace.

### 3. Pillar 3: Autonomous Rule Induction & Auto-Documentation Engine
- **File**: [`services/backend/infrastructure/knowledge/auto_doc.py`](file:///d:/RAYSAN/ai-2d-checker/services/backend/infrastructure/knowledge/auto_doc.py)
- **Role**: Aggregates feedback events. When an entity text pattern is dismissed $\ge 3$ times for a client, `AutoDocEngine` automatically writes a learned rule note into `docs/vault/08 - Client Domain & CAD Rules/Learned_Rules_{client_name}.md` and triggers `VaultSyncManager` live reload.

### 4. Pillar 4: Dynamic Few-Shot RAG Exemplar Memory
- **File**: [`services/backend/infrastructure/audit/comparison/few_shot_retriever.py`](file:///d:/RAYSAN/ai-2d-checker/services/backend/infrastructure/audit/comparison/few_shot_retriever.py)
- **Role**: Queries historical human corrections from MongoDB by `client_name` and dynamically formats client-specific few-shot directives for Gemini LLM system prompts in [`prompt_builder.py`](file:///d:/RAYSAN/ai-2d-checker/services/backend/infrastructure/audit/comparison/full_ai/prompt_builder.py).

---

## 🧪 Verification & Test Suite

> [!WARNING] Three of these four pillars have NO running test coverage (verified 2026-07-29)
> The three files below live in `services/backend/tests/`, which sits **outside**
> `pyproject.toml`'s `testpaths = ["tests"]`. They are not collected by the suite, and they cannot
> be: running them directly fails with `ModuleNotFoundError: No module named 'infrastructure'`
> because they import on a bare `from infrastructure…` path. **They have never executed.**
>
> - `services/backend/tests/test_vault_sync.py` — errors on collection
> - `services/backend/tests/test_audit_feedback.py` — errors on collection
> - `services/backend/tests/test_few_shot_retriever.py` — errors on collection
>
> This note previously listed them as "unit test coverage" without qualification. Do not treat
> Pillars 1, 2 or 4 as verified.

- Actually running: `tests/test_hybrid_pipeline.py`.

---

## 🔧 The flywheel was broken in two places — fixed 2026-07-29

Recorded because both defects were invisible: the loop *looked* wired, logged success, and did
nothing.

**Defect 1 — Pillar 1 read the whole vault, not `08 - Client Domain & CAD Rules/`.**
`_read_all_markdown_contents` walked the entire tree and concatenated every note, then regexed
keywords out of the result. Two consequences. It **did not work**: the inline-code regex ignores
triple-backtick fences, so across the blob it paired one fence's closing backtick with the next
one's opening backtick and captured everything between — **36 of 54 tolerance keywords were
multi-hundred-character markdown spans** containing whole mermaid diagrams and frontmatter. And it
made **documentation a runtime input**: writing a gotcha that quoted a Japanese anchor changed what
`safe_filter` excluded. Improving the vault's prose measurably increased the junk.

Now scoped to `CLIENT_RULES_DIR`, with `_strip_fenced_blocks` applied first and a 2–60 character
bound on any captured span. Measured after: **62 keywords → 18**, injected prose spans **44 → 0**,
with no loss of real vocabulary (`指示外公差`, `指示無き公差` are still extracted — they sit outside
fences and already matched the built-in defaults).

> [!IMPORTANT]
> Architecture notes, gotchas and ADRs are documentation *about* the system. They must never
> steer it. Only `08 - Client Domain & CAD Rules/` is a runtime input.

**Defect 2 — Pillar 3's output was never read back.**
`AutoDocEngine` wrote learned rules such as the `ユニットNo.` title-block dismissal into
`Learned_Rules_General.md`, and nothing consumed them: Pillar 1 extracted only *tolerance*
vocabulary, and its upper-left anchor list is hardcoded. A human could dismiss a callout twenty
times and keep seeing it.

`_parse_learned_rules` now parses the block format `auto_doc.py` writes, and
`get_learned_dismissals(category=None)` exposes it. `safe_filter` consumes it, so the loop closes.

> [!WARNING] Learned patterns are matched EXACTLY, never as substrings
> They come from `AuditFeedbackDocument.entity_text` — the precise string a human dismissed — and
> several are short (`1`, `2A0`). Substring matching would silently suppress unrelated content,
> and **nothing in this system measures its own false-negative rate**, so that failure would not
> show up anywhere. `safe_filter` logs whenever a learned rule fires, because it is the one filter
> driven by stored human decisions rather than by the drawing in front of it.
