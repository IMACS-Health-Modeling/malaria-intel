"""
S3 utilities for malaria-intel data pipeline.
All reads/writes go through these helpers to ensure consistent paths and metadata.
"""

import json
import os
import gzip
import boto3
from datetime import datetime, timezone
from typing import Any

BUCKET = os.environ.get("MALARIA_INTEL_BUCKET", "cdah-malaria-intel-dev")
s3 = boto3.client("s3")


def raw_key(source: str, filename: str, date: str | None = None) -> str:
    """Build a raw layer S3 key: raw/{source}/dt={date}/{filename}"""
    dt = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"raw/{source}/dt={dt}/{filename}"


def processed_key(domain: str, table: str, filename: str) -> str:
    """Build a processed layer S3 key: processed/{domain}/{table}/{filename}"""
    return f"processed/{domain}/{table}/{filename}"


def serving_key(chapter: str, filename: str) -> str:
    """Build a serving layer S3 key: serving/v1/{chapter}/{filename}"""
    return f"serving/v1/{chapter}/{filename}"


def put_json(key: str, data: Any, compress: bool = False) -> None:
    """Write JSON (optionally gzipped) to S3."""
    body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    kwargs: dict = {
        "Bucket": BUCKET,
        "Key": key,
        "ContentType": "application/json",
    }
    if compress:
        body = gzip.compress(body)
        kwargs["ContentEncoding"] = "gzip"
        kwargs["Key"] = key if key.endswith(".gz") else key + ".gz"
    kwargs["Body"] = body
    s3.put_object(**kwargs)
    print(f"  ✓ s3://{BUCKET}/{kwargs['Key']}")


def put_meta(source_key: str, meta: dict) -> None:
    """Write a _meta.json sidecar alongside a data file."""
    meta_key = source_key.rsplit("/", 1)[0] + "/_meta.json"
    meta.setdefault("written_at", datetime.now(timezone.utc).isoformat())
    put_json(meta_key, meta)


def get_json(key: str) -> Any:
    """Read JSON from S3 (handles gzip)."""
    resp = s3.get_object(Bucket=BUCKET, Key=key)
    body = resp["Body"].read()
    if resp.get("ContentEncoding") == "gzip" or key.endswith(".gz"):
        body = gzip.decompress(body)
    return json.loads(body)


def key_exists(key: str) -> bool:
    """Check if an S3 key exists."""
    try:
        s3.head_object(Bucket=BUCKET, Key=key)
        return True
    except s3.exceptions.NoSuchKey:
        return False
    except Exception:
        return False


def list_dates(source: str) -> list[str]:
    """List all date partitions for a raw source: raw/{source}/dt=YYYY-MM-DD/"""
    prefix = f"raw/{source}/"
    paginator = s3.get_paginator("list_objects_v2")
    dates = set()
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix, Delimiter="/"):
        for cp in page.get("CommonPrefixes", []):
            part = cp["Prefix"].rstrip("/").split("dt=")[-1]
            if len(part) == 10:
                dates.add(part)
    return sorted(dates)


def latest_raw(source: str, filename: str) -> str:
    """Return the S3 key for the most recent date partition of a raw file."""
    dates = list_dates(source)
    if not dates:
        raise FileNotFoundError(f"No partitions found for raw/{source}/")
    return raw_key(source, filename, date=dates[-1])
