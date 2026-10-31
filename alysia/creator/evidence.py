from __future__ import annotations

import csv
import io
from pathlib import Path

from alysia.core.io import atomic_write_text
from alysia.creator.models import CreatorJob


BETA_COLUMNS = (
    "run_id",
    "job_id",
    "topic",
    "created_at",
    "approved_at",
    "published_at",
    "platform",
    "platform_content_id",
    "video_artifact",
    "qa_result",
    "publish_result",
    "metrics_available",
    "reflection_available",
    "failure_count",
    "recovery_result",
    "evidence_path",
)


class BetaEvidenceLedger:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.is_file():
            self._write([])

    def upsert(self, job: CreatorJob, *, evidence_path: Path) -> None:
        if job.testing or job.dry_run:
            raise ValueError("testing/dry-run CreatorJob cannot count as a real Beta run")
        if job.platform != "bilibili" or job.status != "PUBLISHED":
            raise ValueError("only a real PUBLISHED Bilibili CreatorJob can enter real Beta evidence")
        if not job.platform_content_id or not job.publication_evidence_path:
            raise ValueError("real Beta requires a platform receipt")
        if not evidence_path.is_file() or evidence_path.stat().st_size == 0:
            raise ValueError("real Beta evidence_path is missing")
        rows = self.rows()
        row = {
            "run_id": job.run_id or "",
            "job_id": job.job_id,
            "topic": job.topic,
            "created_at": job.created_at.isoformat(),
            "approved_at": job.approved_at.isoformat() if job.approved_at else "",
            "published_at": job.published_at.isoformat() if job.published_at else "",
            "platform": job.platform,
            "platform_content_id": job.platform_content_id,
            "video_artifact": str(job.video_path or ""),
            "qa_result": "PASS" if job.qa_report and job.qa_report.passed else "FAIL",
            "publish_result": job.publish_status,
            "metrics_available": str(bool(job.metrics)).lower(),
            "reflection_available": str(job.reflection is not None).lower(),
            "failure_count": str(job.failure_count),
            "recovery_result": job.recovery_result or "",
            "evidence_path": str(evidence_path.resolve()),
        }
        by_id = {item["job_id"]: item for item in rows}
        by_id[job.job_id] = row
        self._write([by_id[key] for key in sorted(by_id)])

    def rows(self) -> list[dict[str, str]]:
        with self.path.open("r", encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))

    def qualified_count(self) -> int:
        count = 0
        for row in self.rows():
            evidence = Path(row["evidence_path"])
            if (
                row["platform"] == "bilibili"
                and row["platform_content_id"].startswith("BV")
                and row["qa_result"] == "PASS"
                and row["publish_result"] == "PUBLISHED"
                and row["metrics_available"] == "true"
                and row["reflection_available"] == "true"
                and evidence.is_file()
                and evidence.stat().st_size > 0
            ):
                count += 1
        return count

    def _write(self, rows: list[dict[str, str]]) -> None:
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=BETA_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        atomic_write_text(self.path, stream.getvalue())

