"""Account deletion: configuration, constants and the phase/timing policy (design rev 3, sections 5.2-5.5)."""
from __future__ import annotations

import os
from dataclasses import dataclass

# ---- request table item shapes (design 5.2) ------------------------------------------------------------
SK_REQUEST = "request"
SK_JOB = "job#"            # child item per discovered edit-plan job id
SK_GKEY = "gkey#"          # child item per discovered global billing binding: gkey#token#<t> | gkey#txn#<id>
RECEIPT_PK = "receipt#"    # pointer item pk = receipt#<request_id>, sk = "pointer"
SK_POINTER = "pointer"

STATE_ACTIVE, STATE_COMPLETED, STATE_CLOSED = "active", "completed", "closed"

# Ordered phases (design 5.4). phase_seq = index + 1 and only ever increases.
PHASES = ("quiesce", "content", "billing", "ratelimit", "wait", "verify", "cognito", "finalize", "final_check")


def phase_seq(phase: str) -> int:
    return PHASES.index(phase) + 1


# ---- timing policy -------------------------------------------------------------------------------------
LAMBDA_TIMEOUT_S = 300
RUN_BUDGET_S = 240                 # no phase starts after this much wall time in one run
LEASE_S = 360                      # > Lambda timeout, so a live run never loses its lease
NOT_BEFORE_DELAY_S = 70 * 60       # delay before verification (tokens + presigned URLs: 60 min, plus margin)
VERIFY_SPACING_S = 10 * 60         # between verification passes
CLEAN_PASSES_REQUIRED = 2
FINAL_CHECK_DELAY_S = 24 * 3600
BACKOFF_S = (5 * 60, 15 * 60, 30 * 60, 60 * 60, 120 * 60)
BACKOFF_CAP_S = 6 * 3600
STALL_FAIL_COUNT = 5
OVERDUE_S = 6 * 3600


def backoff_s(fail_count: int) -> int:
    """Delay after the fail_count-th consecutive failure (1-based): 5, 15, 30, 60, 120 min, then every 6 h."""
    if fail_count <= 0:
        return 0
    return BACKOFF_S[fail_count - 1] if fail_count <= len(BACKOFF_S) else BACKOFF_CAP_S


# ---- billing key shapes (read from master packages/billing/ledger.py; asserted equal in tests) ------------
APPLE_TXN_PK = "__apple_txn__"
APPLE_TOKEN_PK = "__apple_token__"
BILLING_ACCOUNT_SK = "billing#account"
BILLING_ENTITLEMENT_SK = "billing#entitlement"
TXN_SK_PREFIX = "billing#txn#"
TOKEN_SK_PREFIX = "billing#token#"

# edit-plan job states (packages/edit_plan_jobs TERMINAL); staging key shape jobs/<job_id>/...
JOB_TERMINAL = ("completed", "failed", "cancelled", "expired")
STAGING_PREFIX = "jobs/"


@dataclass(frozen=True)
class DeletionConfig:
    env: str
    region: str
    requests_table: str
    users_table: str
    claims_table: str
    usage_table: str
    media_table: str
    stories_table: str
    understanding_table: str
    rate_limit_table: str
    jobs_table: str
    media_bucket: str
    staging_bucket: str
    user_pool_id: str

    @classmethod
    def for_env(cls, env: str, *, account: str, region: str, user_pool_id: str) -> "DeletionConfig":
        """Names as the CDK stacks create them (story-api-stack.ts, story-auth-stack.ts)."""
        t = lambda n: f"story-{env}-{n}"  # noqa: E731
        return cls(env=env, region=region, requests_table=t("account-deletions"), users_table=t("users"),
                   claims_table=t("identity-claims"), usage_table=t("user-usage"), media_table=t("media"),
                   stories_table=t("stories"), understanding_table=t("understanding"),
                   rate_limit_table=t("rate-limits"), jobs_table=t("edit-plan-jobs"),
                   media_bucket=f"story-{env}-media-{account}-{region}",
                   staging_bucket=f"story-{env}-edit-plan-staging-{account}-{region}", user_pool_id=user_pool_id)

    @classmethod
    def from_environ(cls) -> "DeletionConfig":
        """The deployed worker's wiring (D2 sets these). A missing value raises: never a default resource."""
        e = os.environ
        req = lambda k: e[k]  # noqa: E731  (KeyError = fail closed)
        return cls(env=req("STORY_ENVIRONMENT"), region=e.get("AWS_REGION", "us-east-1"),
                   requests_table=req("STORY_ACCOUNT_DELETIONS_TABLE"), users_table=req("STORY_USERS_TABLE"),
                   claims_table=req("STORY_IDENTITY_CLAIMS_TABLE"), usage_table=req("STORY_USER_USAGE_TABLE"),
                   media_table=req("STORY_MEDIA_TABLE"), stories_table=req("STORY_STORIES_TABLE"),
                   understanding_table=req("STORY_UNDERSTANDING_TABLE"), rate_limit_table=req("STORY_RATE_LIMIT_TABLE"),
                   jobs_table=req("STORY_JOBS_TABLE"), media_bucket=req("STORY_MEDIA_BUCKET"),
                   staging_bucket=req("STORY_STAGING_BUCKET"), user_pool_id=req("STORY_COGNITO_USER_POOL_ID"))


def fake_config() -> DeletionConfig:
    """Table names matching account_deletion.fakes.DEFAULT_SCHEMAS (tests only)."""
    return DeletionConfig(env="test", region="us-east-1", requests_table="requests", users_table="users",
                          claims_table="claims", usage_table="usage", media_table="media", stories_table="stories",
                          understanding_table="understanding", rate_limit_table="ratelimits", jobs_table="jobs",
                          media_bucket="media-bucket", staging_bucket="staging-bucket", user_pool_id="pool")
