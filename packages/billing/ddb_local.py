"""Test support: locate or start DynamoDB Local so billing and job-store tests run against REAL DynamoDB expression, condition
and transaction semantics instead of an in-memory double.

Resolution order (first that works; otherwise tests SKIP with the exact reason, they never silently pass):
  1. DDB_LOCAL_ENDPOINT   an already running DynamoDB Local, e.g. http://127.0.0.1:8000
  2. DDB_LOCAL_DIR [+ JAVA_BIN]   a directory containing DynamoDBLocal.jar; started on a free port, stopped at exit
Nothing here ever talks to AWS: every client uses a dummy credential and a loopback endpoint, and every test creates its own
uniquely named table (so a real `story-*-user-usage` table can never be touched).
"""
from __future__ import annotations

import atexit
import os
import shutil
import socket
import subprocess
import time
import uuid
from typing import Optional

_proc: Optional[subprocess.Popen] = None
_endpoint: Optional[str] = None
_reason = ""


def _client(endpoint: str):
    import boto3
    from botocore.config import Config
    return boto3.client("dynamodb", endpoint_url=endpoint, region_name="us-east-1", aws_access_key_id="local",
                        aws_secret_access_key="local", config=Config(retries={"max_attempts": 1}, max_pool_connections=64))


def _reachable(endpoint: str) -> bool:
    try:
        _client(endpoint).list_tables(Limit=1)
        return True
    except Exception:  # noqa: BLE001
        return False


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def endpoint() -> Optional[str]:
    """Return a reachable DynamoDB Local endpoint or None (see `skip_reason`)."""
    global _proc, _endpoint, _reason
    if _endpoint:
        return _endpoint
    ep = os.environ.get("DDB_LOCAL_ENDPOINT", "").strip()
    if ep:
        if not ep.startswith(("http://127.0.0.1", "http://localhost")):
            _reason = f"DDB_LOCAL_ENDPOINT={ep} is not a loopback address; refusing to run billing tests against it"
            return None
        if _reachable(ep):
            _endpoint = ep
            return ep
        _reason = f"DDB_LOCAL_ENDPOINT={ep} is not reachable"
        return None
    d = os.environ.get("DDB_LOCAL_DIR", "").strip()
    java = os.environ.get("JAVA_BIN", "").strip() or shutil.which("java") or ""
    if d and os.path.isfile(os.path.join(d, "DynamoDBLocal.jar")) and java:
        port = _free_port()
        _proc = subprocess.Popen([java, f"-Djava.library.path={os.path.join(d, 'DynamoDBLocal_lib')}", "-jar",
                                  os.path.join(d, "DynamoDBLocal.jar"), "-inMemory", "-disableTelemetry", "-port", str(port)],
                                 cwd=d, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        atexit.register(stop)
        ep = f"http://127.0.0.1:{port}"
        for _ in range(60):
            if _reachable(ep):
                _endpoint = ep
                return ep
            time.sleep(0.25)
        _reason = "DynamoDB Local was started but never became reachable"
        stop()
        return None
    _reason = ("DynamoDB Local unavailable: set DDB_LOCAL_ENDPOINT (running instance) or DDB_LOCAL_DIR (+ JAVA_BIN). "
               "See specs/.../billing-v1-spec.md section 'DynamoDB Local procedure'.")
    return None


def skip_reason() -> str:
    return _reason


def stop() -> None:
    global _proc
    if _proc is not None:
        try:
            _proc.terminate()
            _proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            pass
        _proc = None


def client(ep: str):
    return _client(ep)


def create_usage_table(c, name: Optional[str] = None) -> str:
    """The shared UserUsage table shape: PK story_user_id (S), SK quota_period (S). Unique name per call."""
    name = name or f"t-usage-{uuid.uuid4().hex[:12]}"
    c.create_table(TableName=name, BillingMode="PAY_PER_REQUEST",
                   AttributeDefinitions=[{"AttributeName": "story_user_id", "AttributeType": "S"},
                                         {"AttributeName": "quota_period", "AttributeType": "S"}],
                   KeySchema=[{"AttributeName": "story_user_id", "KeyType": "HASH"},
                              {"AttributeName": "quota_period", "KeyType": "RANGE"}])
    return name


def create_jobs_table(c, name: Optional[str] = None) -> str:
    name = name or f"t-jobs-{uuid.uuid4().hex[:12]}"
    c.create_table(TableName=name, BillingMode="PAY_PER_REQUEST",
                   AttributeDefinitions=[{"AttributeName": "job_id", "AttributeType": "S"}],
                   KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}])
    return name


def create_moments_table(c, name: Optional[str] = None) -> str:
    """Account media table shape is not needed for billing; placeholder kept for the verified-media binding tests."""
    name = name or f"t-media-{uuid.uuid4().hex[:12]}"
    c.create_table(TableName=name, BillingMode="PAY_PER_REQUEST",
                   AttributeDefinitions=[{"AttributeName": "story_user_id", "AttributeType": "S"},
                                         {"AttributeName": "cloud_media_id", "AttributeType": "S"}],
                   KeySchema=[{"AttributeName": "story_user_id", "KeyType": "HASH"},
                              {"AttributeName": "cloud_media_id", "KeyType": "RANGE"}])
    return name
