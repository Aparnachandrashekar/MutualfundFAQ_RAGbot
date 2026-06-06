"""Compatibility entry: `python3 -m phase1.ingestion.run_1_1` → Phase 1.1 runner."""

from phase1.ingestion.subphase_1_1_fetch.run import main

if __name__ == "__main__":
    raise SystemExit(main())
