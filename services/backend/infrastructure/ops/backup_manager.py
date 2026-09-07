from pathlib import Path

from services.backend.config import settings


# History, kept as a comment rather than a docstring on purpose: quoting a capability claim is not
# the same as making one, and `tests/test_no_fake_ai_capability.py` draws exactly that line.
#
# This class used to advertise "automated, encrypted local backups of the MongoDB datasets,
# LanceDB vector shards, and cached configurations". None of it existed. `create_secure_backup`
# created an empty directory, logged "System state successfully archived: <path>.zip", and
# returned that path — for a file it never wrote. The compression and the AES-256-GCM encryption
# were a two-line comment beginning "In production:". Found by the R0 capability guard.
class BackupManager:
    """
    Lists local backup archives. Creating them is not implemented.
    """

    @staticmethod
    def create_secure_backup() -> str:
        """
        Not implemented. Raises rather than reporting a success it cannot deliver.

        A backup routine is the worst possible place for a stub that returns cleanly: the failure
        is silent when the backup is taken and only surfaces at restore time, when the data is
        already gone. Raising means an integrator finds out immediately instead.
        """
        raise NotImplementedError(
            "BackupManager.create_secure_backup does not create backups. It never has — it "
            "returned a path to an archive it did not write, having already logged that the "
            "archive succeeded. Implement real compression and encryption before wiring this to "
            "anything, and do not restore the previous behaviour: a backup that reports success "
            "without writing bytes is worse than no backup at all, because it is trusted."
        )

    @staticmethod
    def list_backups() -> list:
        """
        Lists all available local restore points inside the sandbox.
        """
        backup_dir = Path(settings.STORAGE_ROOT).resolve() / "backups"
        if not backup_dir.exists():
            return []
        return [str(f) for f in backup_dir.glob("*.zip")]
