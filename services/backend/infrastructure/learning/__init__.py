"""Human-in-the-loop learned-correction layer (deterministic, no LLM).

Every human correction of a comparison finding (dismiss, flip verdict, confirm a change,
reclassify, correct a value) is captured as a labeled example on AuditFeedbackDocument.
A lightweight scikit-learn classifier trains on those labels and, at comparison time,
adjusts noisy deterministic findings — flipping false CHANGED→MATCHED, promoting confirmed
changes, and reclassifying — gated by confidence so it abstains while undertrained.

Design notes:
- The model + its human-readable Model Card live in the Obsidian vault under
  `09 - Learned Models/` (the user's "second brain"), resolved via VaultSyncManager.vault_path.
- Inference runs POST-cache and its output is never written to the comparison cache, so a
  retrain takes effect immediately for every drawing pair without a COMPARISON_CACHE_VERSION
  bump (see docs plan + vault gotcha note).
"""
