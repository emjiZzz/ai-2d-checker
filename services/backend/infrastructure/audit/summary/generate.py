"""The model call, and the deterministic text that stands in for it — ADR-010 decision 2.

The prompt hands over the finding list and nothing else. There is no image part, no entity dump
and no retrieved prose in this module, and there should never be one: the coverage check in
`verify.py` cannot distinguish "the model described something outside the finding list" from "the
differ missed something" if the model can see more than the list.
"""
from __future__ import annotations

import json

from ....config import settings
from ....logger import logger
from .models import Finding, GroundedSummary

# ADR-010 leaves language and audience explicitly undecided. English matches the rest of this
# console ("Drawing Infraction Feed", "Correction Guideline"); the domain is Japanese CAD, so this
# is a default rather than an answer, and it is a parameter so changing it is a call-site edit.
DEFAULT_LANGUAGE = "English"

SYSTEM_INSTRUCTION = """You summarise the results of a CAD drawing comparison for a human checker.

You are given a complete list of findings. Each has an id, a category, a status and a description.

Rules, in order of importance:
1. Do NOT invent findings. Every claim you write must be about findings in the supplied list.
2. Do NOT omit findings. Every supplied finding id must appear in the `finding_ids` of at least
   one claim. Group related findings into a single claim wherever that reads better -- one claim
   may cite many ids -- but nothing may go unmentioned.
3. Cite by id. Each claim carries the ids it is about in `finding_ids`.
4. Do not count. `total_findings_stated` is supplied to you below; echo it exactly.
5. Say what the changes MEAN together where you can: that four dimension edits are one revision to
   one feature, or that a plate thickness changed while the BOM weight did not follow it. That
   relation is the only thing you add. If you cannot see a relation, state the change plainly.
6. Be concise. A checker is glancing at this, not reading it.

You are not deciding whether anything changed. That has already been determined. You are
describing findings that already exist."""


class SummaryUnavailableError(RuntimeError):
    """No provider could answer. Distinct from "the summary failed verification" — one is an
    infrastructure fact, the other is a statement about the output."""


def build_prompt(findings: list[Finding], language: str = DEFAULT_LANGUAGE) -> str:
    payload = [
        {"id": f.id, "category": f.category, "status": f.status, "description": f.description}
        for f in findings
    ]
    return (
        f"Write the summary in {language}.\n\n"
        f"total_findings_stated MUST be exactly {len(findings)}.\n\n"
        f"Findings ({len(findings)}):\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def generate(
    findings: list[Finding], language: str = DEFAULT_LANGUAGE
) -> tuple[GroundedSummary, str]:
    """Ask the model for a grounded summary. Returns `(summary, model_used)`.

    Raises `SummaryUnavailableError` when no provider can answer. The caller turns that into
    `SummaryStatus.UNAVAILABLE`, which is normal operation -- ADR-010 decision 4.
    """
    api_key = settings.GEMINI_API_KEY
    openai_key = settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY")
    if openai_key == "YOUR_OPENAI_API_KEY_HERE":
        openai_key = None

    if not (api_key and api_key != "YOUR_GEMINI_API_KEY_HERE") and not openai_key:
        raise SummaryUnavailableError("Neither Gemini nor OpenAI API key is configured.")

    prompt = build_prompt(findings, language)
    last_error: Exception | None = None

    # 1. Try Gemini cascade first if configured
    if api_key and api_key != "YOUR_GEMINI_API_KEY_HERE":
        try:
            from google import genai  # noqa: PLC0415
            from google.genai import types  # noqa: PLC0415

            client = genai.Client(api_key=api_key)
            for model in settings.GEMINI_MODEL_CASCADE:
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=[prompt],
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_INSTRUCTION,
                            response_mime_type="application/json",
                            response_schema=GroundedSummary,
                            temperature=0.0,
                        ),
                    )
                    return GroundedSummary.model_validate_json(response.text), model
                except Exception as err:  # noqa: BLE001
                    last_error = err
                    logger.warning(f"[summary] Gemini model {model} failed: {err}")
        except Exception as genai_init_err:
            last_error = genai_init_err
            logger.warning(f"[summary] Gemini client initialization failed: {genai_init_err}")

    # 2. Fallback to OpenAI if configured
    if openai_key:
        try:
            import httpx
            target_model = getattr(settings, "OPENAI_MODEL", "gpt-5.4") or "gpt-4o"
            logger.info(f"[summary] Attempting summary generation via OpenAI model: {target_model}")
            payload = {
                "model": target_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_INSTRUCTION},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.0
            }
            headers = {
                "Authorization": f"Bearer {openai_key.strip()}",
                "Content-Type": "application/json"
            }
            with httpx.Client(timeout=60.0) as http_client:
                res = http_client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
                res.raise_for_status()
                res_data = res.json()
                content = res_data["choices"][0]["message"]["content"]
                return GroundedSummary.model_validate_json(content), f"openai/{target_model}"
        except Exception as openai_err:
            last_error = openai_err
            logger.warning(f"[summary] OpenAI fallback failed: {openai_err}")

    raise SummaryUnavailableError(f"Every model provider failed. Last error: {last_error}")


def deterministic_summary(findings: list[Finding]) -> str:
    """The always-available fallback.

    This is not a legacy path waiting to be removed. ADR-010 ships generation behind a flag with
    **no measurement** that it is better, so this stays as the permanent floor: offline, free,
    deterministic, and incapable of omitting a finding.
    """
    if not findings:
        return "No differences were found between the reference and revision drawings."

    by_category: dict[str, int] = {}
    for f in findings:
        by_category[f.category] = by_category.get(f.category, 0) + 1

    parts = ", ".join(
        f"{count} in {category}" for category, count in sorted(by_category.items())
    )
    noun = "finding" if len(findings) == 1 else "findings"
    return f"{len(findings)} {noun}: {parts}."
