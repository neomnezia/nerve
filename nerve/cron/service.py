"""Cron scheduler — APScheduler integration.

Runs cron jobs and source runners on schedule.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from nerve.agent.engine import AgentEngine
from nerve.config import NerveConfig
from nerve.cron.jobs import CronJob, load_jobs
from nerve.db import Database

if TYPE_CHECKING:
    from nerve.sources.runner import SourceRunner

logger = logging.getLogger(__name__)


def _parse_interval(interval: str) -> int:
    """Parse an interval string like '2h', '30m', '1h30m' into seconds."""
    import re
    total = 0
    parts = re.findall(r"(\d+)([hms])", interval.lower())
    for value, unit in parts:
        v = int(value)
        if unit == "h":
            total += v * 3600
        elif unit == "m":
            total += v * 60
        elif unit == "s":
            total += v
    return total or 7200  # Default 2h


class CronService:
    """Manages scheduled cron jobs."""

    def __init__(self, config: NerveConfig, engine: AgentEngine, db: Database):
        self.config = config
        self.engine = engine
        self.db = db
        self.scheduler = AsyncIOScheduler()
        self._jobs: list[CronJob] = []
        self._source_runners: list[SourceRunner] = []

    async def start(self) -> None:
        """Load jobs and start the scheduler."""
        # Load job definitions
        self._jobs = load_jobs(self.config.cron.jobs_file)

        # Register cron jobs
        for job in self._jobs:
            if not job.enabled:
                continue

            try:
                trigger = CronTrigger.from_crontab(job.schedule)
            except ValueError:
                # Try as interval
                seconds = _parse_interval(job.schedule)
                trigger = IntervalTrigger(seconds=seconds)

            self.scheduler.add_job(
                self._run_job_wrapper,
                trigger,
                args=[job],
                id=job.id,
                name=job.description or job.id,
                replace_existing=True,
            )
            logger.info("Scheduled job: %s (%s)", job.id, job.schedule)

        # Register source runners (pure ingestors — no engine needed)
        try:
            from nerve.sources.registry import build_source_runners

            self._source_runners = build_source_runners(self.config, self.db)

            for runner in self._source_runners:
                source_name = runner.source.source_name
                # Source names can be compound (e.g. "gmail:account@email.com").
                # The config key is the base type before the colon.
                config_key = source_name.split(":")[0]
                source_config = getattr(self.config.sync, config_key, None)
                if source_config is None:
                    continue
                schedule_str = getattr(source_config, "schedule", "*/15 * * * *")

                try:
                    trigger = CronTrigger.from_crontab(schedule_str)
                except ValueError:
                    seconds = _parse_interval(schedule_str)
                    trigger = IntervalTrigger(seconds=seconds)

                self.scheduler.add_job(
                    self._run_source_wrapper,
                    trigger,
                    args=[runner],
                    id=runner.job_id,
                    name=f"Source: {source_name}",
                    replace_existing=True,
                )
                logger.info("Scheduled source: %s (%s)", source_name, schedule_str)
        except Exception as e:
            logger.warning("Failed to register source runners: %s", e, exc_info=True)

        # Daily cleanup of expired messages and consumer cursors
        self.scheduler.add_job(
            self._cleanup_expired,
            CronTrigger(hour=3, minute=0),
            id="cleanup",
            name="Cleanup expired data",
            replace_existing=True,
        )

        self.scheduler.start()
        logger.info(
            "Cron service started with %d jobs + %d sources",
            len(self._jobs), len(self._source_runners),
        )

    async def stop(self) -> None:
        """Stop the scheduler."""
        self.scheduler.shutdown(wait=False)
        logger.info("Cron service stopped")

    async def _maybe_rotate_context(
        self, session_id: str, rotate_hours: int,
    ) -> bool:
        """Check if a persistent cron session's context should be rotated.

        Rotation clears the sdk_session_id so the next run starts a fresh
        SDK client.  Old messages remain in the DB for memU search.

        Returns True if rotation was performed.
        """
        session = await self.db.get_session(session_id)
        if not session or not session.get("connected_at"):
            return False

        connected_at_str = session["connected_at"]
        try:
            ts = connected_at_str
            if "T" not in ts:
                ts = ts.replace(" ", "T")
            if not ts.endswith(("Z", "+00:00")):
                ts += "+00:00"
            connected_at = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            logger.warning(
                "Invalid connected_at for %s: %s", session_id, connected_at_str,
            )
            return False

        age_hours = (
            datetime.now(timezone.utc) - connected_at
        ).total_seconds() / 3600

        if age_hours < rotate_hours:
            return False

        # Memorize current context before rotation (safety net)
        try:
            await self.engine._memorize_session(session_id)
        except Exception as e:
            logger.warning("Pre-rotation memorize failed for %s: %s", session_id, e)

        # Clear sdk_session_id + connected_at → next run starts fresh
        await self.engine.sessions.mark_idle(session_id, preserve_sdk_id=False)
        logger.info(
            "Rotated context for persistent cron %s (age: %.1fh >= %dh)",
            session_id, age_hours, rotate_hours,
        )
        return True

    async def _run_job_wrapper(self, job: CronJob) -> None:
        """Wrapper to run a cron job with logging."""
        log_id = await self.db.log_cron_start(job.id)
        logger.info("Running cron job: %s (mode=%s)", job.id, job.session_mode)

        try:
            model = job.model or self.config.agent.cron_model
            rotated = False

            if job.session_mode == "persistent":
                # Persistent mode: reuse SDK context across runs
                if job.context_rotate_hours > 0:
                    rotated = await self._maybe_rotate_context(
                        f"cron:{job.id}", job.context_rotate_hours,
                    )

                # Determine prompt: full on first run, short reminder on subsequent
                prompt = job.prompt
                if job.reminder_mode:
                    session = await self.db.get_session(f"cron:{job.id}")
                    is_resume = (
                        session
                        and session.get("sdk_session_id")
                        and not rotated
                    )
                    if is_resume:
                        prompt = (
                            "Scheduled run — continue with the same "
                            "task as before."
                        )
                    else:
                        prompt = job.prompt.rstrip() + (
                            "\n\n---\n"
                            "NOTE: This is a persistent cron with reminder "
                            "mode. On subsequent triggers you will receive "
                            "a short reminder instead of this full prompt. "
                            "Continue executing these instructions each time."
                        )

                response = await self.engine.run_persistent_cron(
                    job_id=job.id,
                    prompt=prompt,
                    model=model,
                )
            else:
                # Isolated mode: per-run session (existing behaviour)
                run_id = (
                    datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                    if self.config.sessions.cron_session_mode == "per_run"
                    else None
                )
                response = await self.engine.run_cron(
                    job_id=job.id,
                    prompt=job.prompt,
                    model=model,
                    run_id=run_id,
                )

            output = response[:2000]
            if rotated:
                output = "[context rotated] " + output
            await self.db.log_cron_finish(log_id, "success", output=output)
            logger.info("Cron job %s completed (%d chars)", job.id, len(response))

        except Exception as e:
            logger.error("Cron job %s failed: %s", job.id, e, exc_info=True)
            await self.db.log_cron_finish(log_id, "error", error=str(e))

    async def _run_source_wrapper(self, runner: SourceRunner) -> None:
        """Wrapper to run a source ingestion with cron and source logging."""
        log_id = await self.db.log_cron_start(runner.job_id)
        logger.info("Running source: %s", runner.source.source_name)

        try:
            result = await runner.run()
            summary = f"{result.records_ingested} ingested"
            if result.error:
                summary += f", error: {result.error}"

            status = "success" if result.error is None else "error"
            await self.db.log_cron_finish(log_id, status, output=summary[:2000])
            await self.db.log_source_run(
                source=runner.source.source_name,
                records_fetched=result.records_ingested,
                records_processed=result.records_ingested,
                error=result.error,
            )
            logger.info("Source %s done: %s", runner.source.source_name, summary)
        except Exception as e:
            logger.error("Source %s failed: %s", runner.source.source_name, e, exc_info=True)
            await self.db.log_cron_finish(log_id, "error", error=str(e))
            await self.db.log_source_run(
                source=runner.source.source_name,
                error=str(e),
            )

    async def _cleanup_expired(self) -> None:
        """Clean up expired source messages and consumer cursors."""
        try:
            msg_count = await self.db.cleanup_expired_messages()
            cursor_count = await self.db.cleanup_expired_consumer_cursors()
            if msg_count or cursor_count:
                logger.info(
                    "Cleanup: %d expired messages, %d expired consumer cursors",
                    msg_count, cursor_count,
                )
        except Exception as e:
            logger.error("Cleanup failed: %s", e, exc_info=True)

    async def run_job(self, job_id: str) -> None:
        """Run a specific job manually (used by CLI)."""
        job = next((j for j in self._jobs if j.id == job_id), None)
        if not job:
            # Try loading fresh
            self._jobs = load_jobs(self.config.cron.jobs_file)
            job = next((j for j in self._jobs if j.id == job_id), None)

        if not job:
            raise ValueError(f"Job not found: {job_id}")

        await self._run_job_wrapper(job)

    async def rotate_session(self, job_id: str) -> dict:
        """Force-rotate a persistent cron session's context.

        Runs pre-rotation memorization, then clears the sdk_session_id
        so the next run starts a fresh SDK client.

        Returns a dict with rotation details.
        Raises ValueError if job not found or not persistent.
        """
        job = next((j for j in self._jobs if j.id == job_id), None)
        if not job:
            self._jobs = load_jobs(self.config.cron.jobs_file)
            job = next((j for j in self._jobs if j.id == job_id), None)

        if not job:
            raise ValueError(f"Job not found: {job_id}")
        if job.session_mode != "persistent":
            raise ValueError(
                f"Job {job_id!r} is not persistent (mode={job.session_mode!r})"
            )

        session_id = f"cron:{job_id}"
        session = await self.db.get_session(session_id)

        # Calculate current age for the response
        session_age_hours: float | None = None
        if session and session.get("connected_at"):
            try:
                ts = session["connected_at"]
                if "T" not in ts:
                    ts = ts.replace(" ", "T")
                if not ts.endswith(("Z", "+00:00")):
                    ts += "+00:00"
                ca = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                session_age_hours = round(
                    (datetime.now(timezone.utc) - ca).total_seconds() / 3600, 2,
                )
            except (ValueError, TypeError):
                pass

        # Force rotation (rotate_hours=0 ensures any positive age passes)
        rotated = await self._maybe_rotate_context(session_id, rotate_hours=0)

        logger.info(
            "Manual rotation for %s: rotated=%s age=%.1fh",
            job_id, rotated,
            session_age_hours if session_age_hours is not None else -1,
        )
        return {
            "job_id": job_id,
            "rotated": rotated,
            "session_age_hours": session_age_hours,
        }

    def list_jobs(self) -> list[dict]:
        """List all registered jobs (cron + sources) with their next run times."""
        result = []
        for job in self._jobs:
            sched_job = self.scheduler.get_job(job.id)
            next_run = sched_job.next_run_time if sched_job else None
            result.append({
                "id": job.id,
                "type": "cron",
                "schedule": job.schedule,
                "description": job.description,
                "enabled": job.enabled,
                "session_mode": job.session_mode,
                "next_run": next_run.isoformat() if next_run else None,
            })

        # Include source runners
        for runner in self._source_runners:
            source_name = runner.source.source_name
            config_key = source_name.split(":")[0]
            sched_job = self.scheduler.get_job(runner.job_id)
            next_run = sched_job.next_run_time if sched_job else None
            source_config = getattr(self.config.sync, config_key, None)
            schedule = getattr(source_config, "schedule", "?") if source_config else "?"
            result.append({
                "id": runner.job_id,
                "type": "source",
                "schedule": schedule,
                "description": f"Source: {source_name} (ingestor)",
                "enabled": True,
                "next_run": next_run.isoformat() if next_run else None,
            })

        return result
