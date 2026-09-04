"""Drawing ingestion — upload, re-extraction and purge of CAD drawings.

Lived at `domain/services/` until 2026-08-14 and was the backend's only layer inversion:
`domain/` is not allowed to import `infrastructure/` (see `.claude/agents/architect-reviewer.md`,
"Layer inversion"), and this module imported the processing queue, the storage path resolver and
the comparison cache manager. It also imports fastapi, which no dependency inversion would
have removed — so the honest fix was to put it where it belongs rather than invert three imports
and leave a web framework in the domain layer.

It sits in `infrastructure/` for the same reason `infrastructure/audit/comparison/orchestrator.py`
does: it is a router-called orchestrator over storage, the database and the job queue, not an
enterprise rule. Its own docstring always said so — *"Decouples storage and CAD pipeline
interactions from the HTTP API router layer"* is the description of an application service.

The direction is now `api/` -> `infrastructure/` -> `domain/` throughout.
"""
