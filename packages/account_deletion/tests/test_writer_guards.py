"""Account deletion writer guards (design 5.5): G1 single-PUT cap, G2 reconcile never recreates a deleted job."""
from __future__ import annotations

import media_store as M
import pytest
from account_deletion.fakes import FakeDDB
from edit_plan_jobs import JobStore, JobStoreConfig

SHA = "a" * 64


class _S3:
    def generate_presigned_url(self, *a, **k):
        return "https://example.invalid/presigned"


def _media():
    ddb = FakeDDB()
    return M.MediaStore(M.MediaStoreConfig(table="media", bucket="b"), ddb=ddb, s3=_S3())


@pytest.mark.parametrize("kind", [M.MEDIA_KIND_MOMENT, M.MEDIA_KIND_GENERATED])
def test_g1_single_put_above_the_multipart_threshold_is_refused(kind):
    s = _media()
    s.initiate_upload(owner="o", content_sha256=SHA, size_bytes=M.MULTIPART_THRESHOLD, media_kind=kind)  # at the cap
    with pytest.raises(M.SinglePutTooLarge):
        s.initiate_upload(owner="o", content_sha256="b" * 64, size_bytes=M.MULTIPART_THRESHOLD + 1, media_kind=kind)


@pytest.mark.parametrize("kind", [M.MEDIA_KIND_MUSIC, M.MEDIA_KIND_AI_ARTIFACT])
def test_g1_single_put_only_kinds_are_not_capped(kind):
    rec, created = _media().initiate_upload(owner="o", content_sha256=SHA, size_bytes=64 * 1024 * 1024,
                                            media_kind=kind)
    assert created


class _SQS:
    def __init__(self):
        self.sent = []

    def send_message(self, QueueUrl, MessageBody):
        self.sent.append(MessageBody)


class _RacingDDB(FakeDDB):
    """The scan sees the job; account deletion removes the row before the reconcile update."""

    def scan(self, **kw):
        out = super().scan(**kw)
        for it in out["Items"]:
            self.tables["jobs"].pop((it["job_id"]["S"], ""), None)
        return out


def test_g2_reconcile_does_not_recreate_a_job_deleted_meanwhile():
    ddb, sqs = _RacingDDB(), _SQS()
    ddb.put("jobs", {"job_id": {"S": "j1"}, "owner": {"S": "u"}, "status": {"S": "queued"},
                     "attempt_count": {"N": "0"}, "created_at": {"N": "1"}})
    js = JobStore(JobStoreConfig(table="jobs", queue_url="q", bucket="b", region="us-east-1"), ddb=ddb, sqs=sqs)
    assert js.reconcile_lost_enqueue() == []
    assert ddb.tables["jobs"] == {} and sqs.sent == []


def test_g2_reconcile_still_reenqueues_a_live_stranded_job():
    ddb, sqs = FakeDDB(), _SQS()
    ddb.put("jobs", {"job_id": {"S": "j1"}, "owner": {"S": "u"}, "status": {"S": "queued"},
                     "attempt_count": {"N": "0"}, "created_at": {"N": "1"}})
    js = JobStore(JobStoreConfig(table="jobs", queue_url="q", bucket="b", region="us-east-1"), ddb=ddb, sqs=sqs)
    assert js.reconcile_lost_enqueue() == ["j1"] and len(sqs.sent) == 1
