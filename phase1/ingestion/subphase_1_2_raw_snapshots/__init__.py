"""Phase 1.2 — raw HTML snapshot storage."""

from phase1.ingestion.subphase_1_2_raw_snapshots.storage import (
    META_FILENAME,
    RAW_FILENAME,
    StoredSnapshotPaths,
    new_run_id,
    stored_snapshot_relative,
    write_raw_snapshot,
)

__all__ = [
    "META_FILENAME",
    "RAW_FILENAME",
    "StoredSnapshotPaths",
    "new_run_id",
    "stored_snapshot_relative",
    "write_raw_snapshot",
]
