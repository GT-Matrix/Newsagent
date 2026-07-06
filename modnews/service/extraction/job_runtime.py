from __future__ import annotations

from modnews.service.extraction.repair_manager import RepairManager
from modnews.service.extraction.repair_policy import should_auto_repair
from modnews.service.extraction.web_contract import ExtractorFailure, WebJob, WebSource


def finish_failure(job: WebJob, source: WebSource, failure: ExtractorFailure, *, store, repair_manager: RepairManager) -> WebJob:
    job.error_type = failure.error_type
    job.error = failure.message
    if failure.unrepairable:
        job.state = "skipped_unrepairable"
        store.save(job)
        store.append(job.id, "repair_skipped", reason=failure.error_type, message=failure.message)
        return job
    if should_auto_repair(source, failure, job.attempts):
        job.state = "repair_queued"
        store.save(job)
        reason = (
            f"Automatic repair for web extraction job {job.id}. "
            f"Failure type: {failure.error_type}. Error: {failure.message}"
        )
        task = repair_manager.create_task(
            source.extractor_id or source.id,
            reason=reason,
            source_metadata=source.to_dict(),
        )
        job.repair_task_id = task.id
        job.state = "repairing"
        store.save(job)
        store.append(job.id, "repair_started", task_id=task.id, source_id=source.id)
        return job
    job.state = "failed"
    store.save(job)
    store.append(job.id, "job_failed", error_type=failure.error_type, message=failure.message)
    return job
