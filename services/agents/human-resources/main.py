from __future__ import annotations

import sys
from pathlib import Path


def _append_repo_root_to_pythonpath() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    repo_root_text = str(repo_root)
    if repo_root_text not in sys.path:
        sys.path.insert(0, repo_root_text)


_append_repo_root_to_pythonpath()

if __name__ == "__main__":
    from src.lifecycle_agent.main import main

    main()
