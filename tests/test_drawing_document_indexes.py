"""Regression: DrawingDocument.file_hash must NOT be a unique index.

Dedup was removed — `DrawingIngestionService.process_ingestion` re-ingests every upload as a
fresh document so a corrected file can be re-uploaded. A leftover `unique=True` on the
file_hash index contradicted that and made re-uploading the same file fail with a MongoDB
E11000 duplicate-key error ("Drawing upload failed"). This pins the index as non-unique so the
constraint can't creep back in.
"""
from services.backend.domain.models.drawing_document import DrawingDocument


def _file_hash_index():
    for idx in DrawingDocument.Settings.indexes:
        doc = idx.document  # pymongo IndexModel -> SON with 'key' + options
        if any(field == "file_hash" for field, _ in doc["key"].items()):
            return doc
    return None


def test_file_hash_index_exists_and_is_not_unique():
    doc = _file_hash_index()
    assert doc is not None, "file_hash index should still exist (used for cache-key lookups)"
    assert doc.get("unique", False) is False, (
        "file_hash index must be non-unique — dedup was removed and re-uploads must succeed"
    )
