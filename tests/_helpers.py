"""
Shared test helper for loading same-named per-service `app` packages
without collisions when the full test suite runs in one process.

Why this exists: every service in services/*/app/ is named plain `app`
(that's correct and fine in production -- each service runs in its own
separate Docker container, so there's never a real collision there).
But when running the WHOLE test suite in one process (`pytest tests/`),
several different `app` packages from different services get imported
into the same interpreter. Python's import cache (sys.modules) only
keeps ONE `app` at a time -- once any test imports `app.X`, a later
test file's `import app.Y` silently reuses the FIRST service's cached
`app` package instead of loading its own, producing confusing
ModuleNotFoundErrors that only appear when tests run together, never
when a single test file is run alone (which is why this class of bug is
easy to miss).

Fix: before each test file imports its own `app.*` modules, call
`use_service(service_dir_name)` to purge any previously-cached `app*`
modules and put this service's directory at the FRONT of sys.path, so
the next `import app.X` resolves fresh, from the right place.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SERVICES_DIR = REPO_ROOT / "services"


def use_service(service_dir_name: str) -> None:
    """
    service_dir_name: e.g. "regime-engine", "risk-engine", "data-pipeline".
    Call this BEFORE `import app.whatever` in a test file.
    """
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]

    service_dir = str(SERVICES_DIR / service_dir_name)
    if service_dir in sys.path:
        sys.path.remove(service_dir)
    sys.path.insert(0, service_dir)