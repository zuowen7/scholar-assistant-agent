"""check_config_sync.py — Verify that runtime config keys are a superset of repo defaults.

Usage:
    python scripts/check_config_sync.py                    # compare repo + runtime
    python scripts/check_config_sync.py --strict           # exit 1 on any mismatch

Called automatically from api_factory.py on startup (non-fatal warning mode).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Locate the repo-root default.yaml relative to this script
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
_REPO_DEFAULT = _REPO_ROOT / "config" / "default.yaml"

# Runtime copy lives beside the python/ directory
_RUNTIME_DEFAULT = _SCRIPT_DIR.parent / "config" / "default.yaml"


def _collect_keys(obj: object, prefix: str = "") -> set[str]:
    """Recursively collect dot-separated keys from a nested dict."""
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            full = f"{prefix}.{k}" if prefix else k
            keys.add(full)
            keys |= _collect_keys(v, full)
    return keys


def check_sync(
    repo_path: Path = _REPO_DEFAULT,
    runtime_path: Path = _RUNTIME_DEFAULT,
    *,
    strict: bool = False,
) -> list[str]:
    """Return list of keys present in repo default but missing from runtime config.

    Returns an empty list when the runtime config is a superset of the repo defaults.
    """
    if not repo_path.exists():
        logger.warning("Repo default config not found: %s", repo_path)
        return []

    with open(repo_path, encoding="utf-8") as f:
        repo_cfg = yaml.safe_load(f) or {}

    if not runtime_path.exists():
        logger.warning("Runtime config not found: %s — skipping sync check", runtime_path)
        return []

    with open(runtime_path, encoding="utf-8") as f:
        runtime_cfg = yaml.safe_load(f) or {}

    repo_keys = _collect_keys(repo_cfg)
    runtime_keys = _collect_keys(runtime_cfg)

    missing = sorted(repo_keys - runtime_keys)
    if missing:
        msg = (
            "Config sync warning: the following keys exist in the repo default "
            "but are missing from the runtime config. Run the app once to auto-regenerate, "
            "or manually add them.\n  " + "\n  ".join(missing)
        )
        if strict:
            logger.error(msg)
        else:
            logger.warning(msg)
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="Exit 1 on mismatch")
    parser.add_argument("--repo", default=str(_REPO_DEFAULT), help="Repo default.yaml path")
    parser.add_argument("--runtime", default=str(_RUNTIME_DEFAULT), help="Runtime default.yaml path")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    missing = check_sync(
        Path(args.repo), Path(args.runtime), strict=args.strict
    )
    if missing and args.strict:
        print(f"ERROR: {len(missing)} config key(s) out of sync.", file=sys.stderr)
        return 1
    if missing:
        print(f"WARNING: {len(missing)} config key(s) missing from runtime config.")
    else:
        print("Config sync OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
