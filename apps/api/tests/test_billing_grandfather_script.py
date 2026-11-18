"""scripts/yotale_billing_grandfather.py end to end against DynamoDB Local: dry run writes nothing, apply is idempotent, only accounts
created before the cutoff are selected, future signups are never grandfathered, and the cohort rollback is exact."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from billing import BillingLedger, ddb_local

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "yotale_billing_grandfather.py"
_spec = importlib.util.spec_from_file_location("gf_script", SCRIPT)
gf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gf)

CUTOFF = "2026-12-01"
BEFORE, AFTER = 1_796_000_000, 1_796_500_000          # 2026-11-30 and 2026-12-06 (UTC)
S = lambda v: {"S": v}  # noqa: E731
N = lambda v: {"N": str(v)}  # noqa: E731


def user(uid, created, status="active", beta="invited"):
    it = {"story_user_id": S(uid), "account_status": S(status), "beta_access_status": S(beta)}
    if created is not None:
        it["created_at"] = N(created)
    return it


USERS = [user("old-1", BEFORE), user("old-2", BEFORE, beta="eligible"), user("susp", BEFORE, status="suspended"),
         user("revoked", BEFORE, beta="revoked"), user("nodate", None), user("new-1", AFTER), user("rehearsal", BEFORE)]


def test_pure_selection_buckets_every_account_and_never_selects_future_signups():
    out = gf.classify_users(USERS, CUTOFF, {"rehearsal"})
    assert out["selected"] == ["old-1", "old-2"]
    assert out["counts"] == {"scanned": 7, "selected": 2, "excluded_by_flag": 1, "not_active": 1, "not_beta_eligible": 1,
                             "missing_created_at": 1, "created_at_or_after_cutoff": 1}
    assert gf.cutoff_ts("2026-12-01") == 1_796_083_200
    boundary = gf.classify_users([user("edge", 1_796_083_200)], CUTOFF, set())          # created exactly AT the cutoff: not before it
    assert boundary["selected"] == []


@pytest.fixture()
def env_tables(ddb_local_endpoint, monkeypatch):
    c = ddb_local.client(ddb_local_endpoint)
    for t in ("story-development-users", "story-development-user-usage"):
        try:
            c.delete_table(TableName=t)
        except Exception:  # noqa: BLE001
            pass
    c.create_table(TableName="story-development-users", BillingMode="PAY_PER_REQUEST",
                   AttributeDefinitions=[{"AttributeName": "story_user_id", "AttributeType": "S"}],
                   KeySchema=[{"AttributeName": "story_user_id", "KeyType": "HASH"}])
    ddb_local.create_usage_table(c, "story-development-user-usage")
    for u in USERS:
        c.put_item(TableName="story-development-users", Item=u)

    class FakeSession:
        def __init__(self, **kw):
            pass

        def client(self, name):
            return c

    import boto3
    monkeypatch.setattr(boto3, "Session", FakeSession)
    return c


def run(args):
    return gf.main(["--environment", "development", "--profile", "x", "--cutoff", CUTOFF, "--exclude", "rehearsal", *args])


def ledger(c):
    return BillingLedger(ddb=c, table="story-development-user-usage")


def test_dry_run_prints_counts_and_writes_nothing(env_tables, capsys):
    assert run([]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "selected: 2" in out and "would change: 2" in out and "create_and_grandfather: 2" in out
    assert "old-1" not in out                                                   # ids hidden by default
    assert env_tables.scan(TableName="story-development-user-usage")["Count"] == 0   # not even an entitlement was created


def test_apply_requires_explicit_confirmation(env_tables, capsys):
    assert run(["--apply"]) == 2
    assert run(["--apply", "--confirm", "beta"]) == 2
    assert env_tables.scan(TableName="story-development-user-usage")["Count"] == 0


def test_apply_grandfathers_only_the_pre_cutoff_cohort_and_is_idempotent(env_tables, capsys):
    assert run(["--apply", "--confirm", "development"]) == 0
    L = ledger(env_tables)
    for u in ("old-1", "old-2"):
        e = L.get_entitlement(u)
        assert e.plan == "beta_grandfathered" and e.unlimited and e.gf_cutoff == CUTOFF
    for u in ("new-1", "rehearsal", "susp", "revoked", "nodate"):
        assert L.get_entitlement(u) is None                                     # never touched, including the future signup
    capsys.readouterr()
    assert run(["--apply", "--confirm", "development"]) == 0                    # re-run
    out = capsys.readouterr().out
    assert "changed: 0" in out and "already in cohort: 2" in out
    assert run([]) == 0
    assert "would change: 0" in capsys.readouterr().out
    # a later signup after the rollout is a normal Free starter
    assert L.ensure_entitlement("new-1").plan == "free_starter"


def test_a_paid_account_is_never_overwritten_by_the_migration(env_tables, capsys):
    L = ledger(env_tables)
    L.admin_grant("old-1", videos=3, moments=3, reason="support")
    assert run(["--apply", "--confirm", "development"]) == 0
    assert L.get_entitlement("old-1").plan == "admin_granted"
    assert L.get_entitlement("old-2").plan == "beta_grandfathered"


def test_rollback_reverts_exactly_this_cohort_dry_run_first(env_tables, capsys):
    run(["--apply", "--confirm", "development"])
    L = ledger(env_tables)
    L.grandfather("old-3-other-cohort", cutoff="2026-01-01")
    capsys.readouterr()
    assert run(["--rollback"]) == 0
    assert "would revert" in capsys.readouterr().out and L.get_entitlement("old-1").plan == "beta_grandfathered"   # dry run: nothing
    assert run(["--rollback", "--apply", "--confirm", "development"]) == 0
    assert "reverted: 2" in capsys.readouterr().out
    for u in ("old-1", "old-2"):
        e = L.get_entitlement(u)
        assert (e.plan, e.unlimited, e.v_avail, e.m_avail) == ("free_starter", False, 2, 30)
    assert L.get_entitlement("old-3-other-cohort").plan == "beta_grandfathered"      # another cohort is untouched
    assert run(["--rollback", "--apply", "--confirm", "development"]) == 0
    assert "reverted: 0" in capsys.readouterr().out                                  # idempotent
