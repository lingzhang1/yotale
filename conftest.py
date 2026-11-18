"""Pytest bootstrap: make the monorepo's Python packages importable.

Simplest working approach for the walking skeleton (no editable installs
required): put the directories that contain the top-level packages onto
sys.path so `import contracts...`, `import story_engine`, `import app...`
all resolve when pytest is run from the repo root.

Layout resolved here:
  <root>/                 -> `contracts` (namespace: contracts.schemas.*)
  <root>/packages         -> `story_engine`, `director_engine`, `edit_engine`,
                             `asset_engine`, `music_engine`, `model_gateway`,
                             `observability`
  <root>/apps/api         -> `app` (the FastAPI application package)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent

for rel in (".", "packages", "apps/api"):
    p = (_ROOT / rel).resolve()
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


# ---------------------------------------------------------------------------------------------------------------------
# Billing / job-store tests run against BOTH the in-memory double and REAL DynamoDB Local (see packages/billing/ddb_local.py).
# The "local" variant skips with an explicit reason when DynamoDB Local is unavailable; set REQUIRE_DDB_LOCAL=1 (CI does) to make
# an unavailable DynamoDB Local a FAILURE instead of a skip, so CI can never silently run only the double.
# ---------------------------------------------------------------------------------------------------------------------
import pytest  # noqa: E402


@pytest.fixture(scope="session")
def ddb_local_endpoint():
    from billing import ddb_local
    ep = ddb_local.endpoint()
    if ep is None:
        msg = ddb_local.skip_reason()
        if os.environ.get("REQUIRE_DDB_LOCAL") == "1":
            pytest.fail(f"REQUIRE_DDB_LOCAL=1 but {msg}")
        pytest.skip(msg)
    return ep


@pytest.fixture(params=["fake", "local"])
def usage_backend(request):
    """(ddb client, table name, kind) with an ISOLATED, uniquely named table per test."""
    from billing import ddb_local
    from billing.fakes import FakeDDB
    if request.param == "fake":
        return FakeDDB(), "t", "fake"
    ep = request.getfixturevalue("ddb_local_endpoint")
    c = ddb_local.client(ep)
    return c, ddb_local.create_usage_table(c), "local"
