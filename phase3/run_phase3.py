#!/usr/bin/env python3
"""
Phase 3 runner script.
"""

from pathlib import Path
import sys

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from phase3.generation.run_pipeline import main

if __name__ == "__main__":
    raise SystemExit(main())
