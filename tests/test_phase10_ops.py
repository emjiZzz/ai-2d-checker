import pytest

# Target Ops Managers
from services.backend.infrastructure.ops.backup_manager import BackupManager
from services.backend.infrastructure.storage.quota_manager import QuotaManager

# Mirrors quota_manager.DEFAULT_QUOTA_LIMIT_BYTES (5 GB); stated here so the expected
# percentages below are readable rather than a chain of multiplications.
QUOTA_LIMIT_BYTES = 5 * 1024 * 1024 * 1024


def test_backup_creation_refuses_rather_than_faking_success():
    """`create_secure_backup` must raise, not return a path to an archive it did not write.

    This test previously monkeypatched *both* BackupManager methods and then asserted on the
    return values of its own lambdas, so it passed without executing a single line of the class.
    What that concealed: the real `create_secure_backup` created an empty directory, logged
    "System state successfully archived", and returned a .zip path for a file it never wrote.
    R0 replaced that with a raise, and this pins it — a silent backup failure is not discovered
    until a restore is attempted, by which point the data is gone.
    """
    with pytest.raises(NotImplementedError, match="does not create backups"):
        BackupManager.create_secure_backup()


def test_backup_listing_reads_the_real_directory(tmp_path, monkeypatch):
    """`list_backups` is real, so exercise it for real: it globs *.zip under storage/backups."""
    monkeypatch.setattr(
        "services.backend.infrastructure.ops.backup_manager.settings.STORAGE_ROOT",
        str(tmp_path),
        raising=False,
    )

    # No directory yet -> empty list, not an error.
    assert BackupManager.list_backups() == []

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    (backup_dir / "ai2d_backup_20260807_101500.zip").write_bytes(b"")
    (backup_dir / "notes.txt").write_text("not an archive")

    backups = BackupManager.list_backups()
    assert len(backups) == 1, "only .zip archives count as restore points"
    assert "ai2d_backup_20260807_101500.zip" in backups[0]


def test_quota_usage_is_computed_from_real_files(tmp_path, monkeypatch):
    """`get_storage_usage` walks the storage tree; verify the arithmetic on known file sizes."""
    monkeypatch.setattr(
        "services.backend.infrastructure.storage.quota_manager.get_storage_root",
        lambda: tmp_path,
    )
    (tmp_path / "nested").mkdir()
    top_level_bytes, nested_bytes = 1024, 2048
    expected_total = top_level_bytes + nested_bytes
    (tmp_path / "a.bin").write_bytes(b"x" * top_level_bytes)
    (tmp_path / "nested" / "b.bin").write_bytes(b"y" * nested_bytes)

    usage = QuotaManager.get_storage_usage()

    assert usage["used_bytes"] == expected_total, "recurses into subdirectories"
    assert usage["quota_limit_bytes"] == QUOTA_LIMIT_BYTES
    assert usage["usage_percentage"] == round((expected_total / QUOTA_LIMIT_BYTES) * 100, 2)


@pytest.mark.parametrize(
    "used_bytes,expected",
    [
        (100 * 1024 * 1024, True),        # well under
        (QUOTA_LIMIT_BYTES - 1, True),    # one byte under the limit
        (QUOTA_LIMIT_BYTES, False),       # exactly at the limit is a breach
        (QUOTA_LIMIT_BYTES + 1, False),   # over
    ],
)
def test_quota_enforcement_boundary(monkeypatch, used_bytes, expected):
    """`enforce_limits` is >=, so the limit itself is a breach. Pinned at the boundary."""
    monkeypatch.setattr(
        "services.backend.infrastructure.storage.quota_manager.QuotaManager.get_storage_usage",
        lambda: {
            "used_bytes": used_bytes,
            "quota_limit_bytes": QUOTA_LIMIT_BYTES,
            "usage_percentage": round((used_bytes / QUOTA_LIMIT_BYTES) * 100, 2),
        },
    )

    assert QuotaManager.enforce_limits() is expected
