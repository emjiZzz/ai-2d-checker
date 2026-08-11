"""
Auto-Documentation Engine (Pillar 3).

Aggregates human engineer feedback events from AuditFeedbackDocument.
When a pattern (e.g. text matching '12.5S' or '指示外公差') is dismissed or corrected
N >= 3 times, AutoDocEngine automatically generates or updates Markdown rule notes
in `docs/vault/08 - Client Domain & CAD Rules/` and triggers VaultSyncManager reload.
"""

from pathlib import Path
from typing import Dict, Any, Optional
try:
    from ...domain.models.audit_feedback import AuditFeedbackDocument
    from .vault_sync import VaultSyncManager
    from ...logger import logger
except Exception:
    from domain.models.audit_feedback import AuditFeedbackDocument
    from infrastructure.knowledge.vault_sync import VaultSyncManager
    try:
        from logger import logger
    except Exception:
        import logging
        logger = logging.getLogger("auto_doc")

#: Dismissals of one pattern, by one client, before it is promoted to a permanent rule.
MIN_DISMISSALS_TO_PROMOTE = 3


def build_dismissal_filter(target_text: str, client_name: Optional[str]) -> Dict[str, Any]:
    """The Mongo filter for *"how many times has **this client** dismissed **this pattern**"*.

    Returned as a plain dict rather than inlined as Beanie expressions, for one reason: this
    filter is the entire defect surface of this module, and the test suite has no database.
    Beanie's class-level comparison operators need `init_beanie`, so a filter built from them
    cannot be inspected offline — which is precisely how the missing `client_name` clause below
    survived. A dict can be asserted on directly.

    Two clauses here are load-bearing and were both absent:

    - **`client_name`** — the rule is filed under `feedback.client_name`, so it must be promoted
      by *that client's* evidence. Counting sheet-wide meant a pattern dismissed **once at each
      of three different clients** reached the threshold and landed in whichever client's file
      happened to trip it, writing customer A's verbatim drawing text into customer B's rules.
      This is the contamination the retired two-tier overlay existed to prevent
      ([[ADR-009 Retiring the Standards Knowledge Track]]); nothing else prevents it now.
    - **`retracted_at`** — a retraction is a human saying *"I clicked that by mistake"*.
      `trainer.py` already skips retracted rows, and a permanent vault rule is a far stronger
      artifact than a training row, so counting them here let three taken-back clicks write a
      rule that suppresses findings forever. `None` matches both null and missing.

    `client_name` is `Optional`, and `None` is matched as itself rather than ignored: an
    unattributed dismissal files under "General", so it must be promoted by other unattributed
    dismissals and not by any named client's.
    """
    return {
        "entity_text": target_text,
        "human_corrected_status": "dismissed",
        "client_name": client_name,
        "retracted_at": None,
    }


async def count_client_dismissals(target_text: str, client_name: Optional[str]) -> int:
    """Non-retracted dismissals of `target_text` by `client_name`. Raises if the DB is unreachable."""
    return await AuditFeedbackDocument.find(
        build_dismissal_filter(target_text, client_name)
    ).count()


class AutoDocEngine:
    """Auto-documents human engineer corrections into Obsidian Second Brain notes."""

    @staticmethod
    async def process_feedback_event(feedback: AuditFeedbackDocument) -> bool:
        """
        Processes an incoming feedback event.
        Checks if the entity_text pattern has accumulated N >= 3 human dismissals for this
        client. If so, auto-writes a learned Markdown rule into
        `docs/vault/08 - Client Domain & CAD Rules/`.

        That directory is the only part of the vault that is a **runtime input** — it feeds
        `get_learned_dismissal_rules()` → `safe_filter` → the zone pools — so a rule written here
        suppresses real findings. Every guard below errs towards not writing.
        """
        try:
            target_text = getattr(feedback, "entity_text", None)
            if not target_text:
                return False

            try:
                dismiss_count = await count_client_dismissals(target_text, feedback.client_name)
            except Exception as err:
                # A count we could not take is NO INFORMATION, never a reason to promote. This
                # branch used to read `dismiss_count = getattr(feedback, "_mock_dismiss_count", 3)`
                # — defaulting to exactly the threshold — so any database hiccup turned a single
                # dismissal into a permanent finding-suppressing rule, through a test hook
                # reachable from the production path. Both the default and the hook are gone.
                logger.error(
                    f"[auto_doc] Could not count dismissals for '{target_text}' "
                    f"({type(err).__name__}: {err}); not promoting."
                )
                return False

            if dismiss_count >= MIN_DISMISSALS_TO_PROMOTE:
                client_label = feedback.client_name or "General"
                # Resolve vault path
                sync_mgr = VaultSyncManager.get_instance()
                vault_dir = sync_mgr.vault_path / "08 - Client Domain & CAD Rules"
                vault_dir.mkdir(parents=True, exist_ok=True)

                filename = f"Learned_Rules_{client_label.replace(' ', '_')}.md"
                target_file = vault_dir / filename

                # Generate learned Markdown content
                rule_text = f"`{feedback.entity_text}`"
                existing_content = ""
                if target_file.exists():
                    with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
                        existing_content = f.read()

                if rule_text not in existing_content:
                    new_rule_entry = (
                        f"\n## Learned Rule — Pattern: {rule_text}\n"
                        f"- **Client**: {client_label}\n"
                        f"- **Category**: `{feedback.category}`\n"
                        f"- **Human Dismissals**: {dismiss_count} confirmed overrides\n"
                        f"- **Directive**: Treat pattern `{feedback.entity_text}` as static legend/template callout. Do not report under `{feedback.category}`.\n"
                    )
                    
                    if not existing_content:
                        existing_content = (
                            f"---\n"
                            f"title: Learned Rules - {client_label}\n"
                            f"type: domain-rules\n"
                            f"tags: [learned-rules, client-rules, hitl]\n"
                            f"---\n\n"
                            f"# 🧠 Learned Rules — Client: {client_label}\n"
                        )
                    
                    updated_content = existing_content + new_rule_entry
                    with open(target_file, "w", encoding="utf-8") as f:
                        f.write(updated_content)

                    logger.info(f"[auto_doc] Auto-documented learned rule for '{feedback.entity_text}' into {target_file}")
                    
                    # Live sync reload (Pillar 1 bridge)
                    sync_mgr.load_live_rules(force_reload=True)
                    return True

        except Exception as err:
            # Deliberately broad: the feedback row is already saved by the time this runs, and
            # auto-documentation failing must not fail the API call. But it is logged with the
            # exception *type* and a traceback, because the caller collapses this to
            # `auto_documented: false` — which is also the normal answer below the threshold.
            # A misspelled attribute in the write path would otherwise be indistinguishable from
            # "this pattern has only been dismissed twice", which is exactly how
            # [[Gotcha - A Swallowed AttributeError Made a Write Path a Permanent No-Op]] hid a
            # write path that had never once run.
            logger.error(
                f"[auto_doc] Failed to process feedback auto-documentation "
                f"({type(err).__name__}: {err})",
                exc_info=True,
            )

        return False
