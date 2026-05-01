"""Structured pipeline logging — writes to stdout and optionally to RDS pipeline_runs table."""

import json
import sys
import time
from datetime import datetime, timezone
from typing import Any


class PipelineLogger:
    def __init__(self, pipeline_name: str, dry_run: bool = False):
        self.name = pipeline_name
        self.dry_run = dry_run
        self.start_ts = time.time()
        self.steps: list[dict] = []
        self._log("start", f"Pipeline '{pipeline_name}' started" + (" [DRY RUN]" if dry_run else ""))

    def _log(self, level: str, msg: str, **kwargs: Any) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "pipeline": self.name,
            "msg": msg,
            **kwargs,
        }
        print(json.dumps(entry), file=sys.stdout)
        self.steps.append(entry)

    def info(self, msg: str, **kwargs: Any) -> None:
        self._log("info", msg, **kwargs)

    def warn(self, msg: str, **kwargs: Any) -> None:
        self._log("warn", msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        self._log("error", msg, **kwargs)

    def step(self, name: str) -> "StepContext":
        return StepContext(self, name)

    def finish(self, records: int = 0, s3_keys: list[str] | None = None) -> None:
        elapsed = round(time.time() - self.start_ts, 2)
        self._log("finish", f"Pipeline complete in {elapsed}s", records=records, elapsed_s=elapsed)
        if not self.dry_run:
            try:
                from pipelines.utils.db import get_conn
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """INSERT INTO malaria.pipeline_runs
                               (pipeline_name, stage, status, records_processed, finished_at, s3_keys)
                               VALUES (%s, %s, %s, %s, NOW(), %s)""",
                            (self.name, "full", "success", records, s3_keys),
                        )
                    conn.commit()
            except Exception as e:
                self._log("warn", f"pipeline_runs write failed: {e}")


class StepContext:
    def __init__(self, logger: PipelineLogger, name: str):
        self.logger = logger
        self.name = name
        self.t0 = time.time()

    def __enter__(self) -> "StepContext":
        self.logger.info(f"→ {self.name}")
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        elapsed = round(time.time() - self.t0, 2)
        if exc_type:
            self.logger.error(f"✗ {self.name} failed in {elapsed}s: {exc_val}")
            return False
        self.logger.info(f"✓ {self.name} done in {elapsed}s")
        return False
