from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.core.models import NewsItem, StepResult
from modnews.core.context import PipelineContext
from modnews.service.extraction.registry import registry_from_project
from modnews.service.extraction.repair import RepairManager
from modnews.service.extraction.repair_policy import classify_exception, should_auto_repair
from modnews.service.extraction.web_contract import ExtractorFailure, WebJob, WebSource
from modnews.service.extraction.web_runner import run_extractor, write_json
from modnews.repository.source_config import source_config_store
from modnews.repository.web_jobs import WebJobStore


class WebExtractionOrchestrator:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.store = WebJobStore(project_root)
        self.registry = registry_from_project(project_root)
        self.repair_manager = RepairManager(project_root, self.registry)

    def run_pipeline_step(self, ctx: PipelineContext, options: dict[str, Any]) -> tuple[list[NewsItem], StepResult]:
        config = source_config_store(self.project_root).load()
        step_config = config["steps"].get("site_lists", {})
        if not step_config.get("enabled", True):
            return [], StepResult(step="site_lists", item_count=0, meta={"enabled": False})

        requested_sites = options.get("sites") or step_config.get("sites") or []
        limit = int(options.get("limit_per_site", step_config.get("limit_per_site", 10)))
        sources = self.enabled_sources(config, requested_sites=requested_sites)
        all_items: list[NewsItem] = []
        errors: list[str] = []
        job_ids: list[str] = []

        for source in sources:
            job = self.run_source(source, scrape_date=ctx.scrape_date, limit=limit)
            job_ids.append(job.id)
            if job.error:
                errors.append(f"{source.id}: {job.error}")
            if job.output_path:
                import json

                try:
                    rows = json.loads(Path(job.output_path).read_text(encoding="utf-8"))
                except Exception:
                    rows = []
                for row in rows if isinstance(rows, list) else []:
                    if not isinstance(row, dict):
                        continue
                    all_items.append(
                        NewsItem(
                            platform=str(row.get("platform") or source.id),
                            title=str(row.get("title") or ""),
                            url=str(row.get("url") or ""),
                            pubtime=row.get("pubtime"),
                            scrape_date=str(row.get("scrape_date") or ctx.scrape_date),
                        )
                    )

        output_path = ctx.work_dir / "site_lists_items.json"
        raw_path = ctx.work_dir / "site_lists_raw.json"
        write_json(output_path, [item.to_dict() for item in all_items])
        write_json(raw_path, {"jobs": job_ids})
        ctx.artifacts["site_lists"] = output_path
        ctx.artifacts["site_lists_raw"] = raw_path
        return all_items, StepResult(
            step="site_lists",
            item_count=len(all_items),
            output_path=str(output_path),
            errors=errors,
            meta={"mode": "managed_extractors", "jobs": job_ids},
        )

    def enabled_sources(self, config: dict[str, Any], requested_sites: list[str] | None = None) -> list[WebSource]:
        raw_sources = config.get("sources", {}).get("site_lists", {})
        requested = set(requested_sites or [])
        sources: list[WebSource] = []
        for source_id, raw in raw_sources.items():
            if not isinstance(raw, dict):
                continue
            if requested and source_id not in requested:
                continue
            source = WebSource.from_config(source_id, raw)
            if source.enabled:
                sources.append(source)
        return sources

    def run_source(self, source: WebSource, *, scrape_date: str, limit: int) -> WebJob:
        max_attempts = int(source.repair_policy.get("max_attempts_before_repair", 3))
        job = self.store.create(source, max_attempts=max_attempts)
        self.store.append(job.id, "scrape_queued", source_id=source.id, extractor_id=source.extractor_id)
        if not source.extractor_id:
            failure = ExtractorFailure("missing_extractor", f"{source.id} has no extractor_id")
            return self._finish_failure(job, source, failure)

        last_failure: ExtractorFailure | None = None
        for attempt in range(1, max_attempts + 1):
            job.attempts = attempt
            job.state = "scraping"
            self.store.save(job)
            self.store.append(job.id, "scrape_started", attempt=attempt, max_attempts=max_attempts)
            try:
                result, raw = run_extractor(registry=self.registry, source=source, scrape_date=scrape_date, limit=limit)
                job_dir = self.store.job_dir(job.id, job.source_id)
                output_path = job_dir / "items.json"
                raw_path = job_dir / "raw_result.json"
                write_json(output_path, [item.to_dict() for item in result.items])
                write_json(raw_path, raw)
                job.state = "succeeded"
                job.item_count = len(result.items)
                job.output_path = str(output_path)
                job.raw_result_path = str(raw_path)
                job.error = None
                job.error_type = None
                self.store.save(job)
                self.store.append(job.id, "scrape_succeeded", item_count=job.item_count)
                return job
            except Exception as exc:
                last_failure = classify_exception(exc)
                job.error_type = last_failure.error_type
                job.error = last_failure.message
                job.state = "failed_retryable" if last_failure.retryable and attempt < max_attempts else "failed_exhausted"
                self.store.save(job)
                self.store.append(job.id, "scrape_failed", attempt=attempt, **last_failure.to_dict())
                if not last_failure.retryable:
                    break

        return self._finish_failure(job, source, last_failure or ExtractorFailure("unknown", "unknown failure"))

    def _finish_failure(self, job: WebJob, source: WebSource, failure: ExtractorFailure) -> WebJob:
        job.error_type = failure.error_type
        job.error = failure.message
        if failure.unrepairable:
            job.state = "skipped_unrepairable"
            self.store.save(job)
            self.store.append(job.id, "repair_skipped", reason=failure.error_type, message=failure.message)
            return job
        if should_auto_repair(source, failure, job.attempts):
            job.state = "repair_queued"
            self.store.save(job)
            reason = (
                f"Automatic repair for web extraction job {job.id}. "
                f"Failure type: {failure.error_type}. Error: {failure.message}"
            )
            task = self.repair_manager.create_task(
                source.extractor_id or source.id,
                reason=reason,
                auto_start=bool(source.repair_policy.get("auto_start", True)),
                source_metadata=source.to_dict(),
            )
            job.repair_task_id = task.id
            job.state = "repairing"
            self.store.save(job)
            self.store.append(job.id, "repair_started", task_id=task.id, source_id=source.id)
            return job
        job.state = "failed"
        self.store.save(job)
        self.store.append(job.id, "job_failed", error_type=failure.error_type, message=failure.message)
        return job
