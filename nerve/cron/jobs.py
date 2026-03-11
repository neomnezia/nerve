"""Cron job definitions and persistence.

Jobs are defined in a YAML file and loaded at startup.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class CronJob:
    """A cron job definition."""
    id: str
    schedule: str  # crontab expression or interval (e.g., "*/30 * * * *", "2h")
    prompt: str  # The message/instruction sent to the agent
    description: str = ""
    model: str = ""  # Override model; empty = use config default
    session_mode: str = "isolated"  # "isolated" (new session per run) or "persistent" (reuse context)
    context_rotate_hours: int = 24  # Hours before persistent context is rotated (0 = never)
    reminder_mode: bool = False  # Persistent only: send short reminder instead of full prompt on subsequent runs
    enabled: bool = True
    metadata: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> CronJob:
        return cls(
            id=d["id"],
            schedule=d["schedule"],
            prompt=d["prompt"],
            description=d.get("description", ""),
            model=d.get("model", ""),
            session_mode=d.get("session_mode", "isolated"),
            context_rotate_hours=int(d.get("context_rotate_hours", 24)),
            reminder_mode=bool(d.get("reminder_mode", False)),
            enabled=d.get("enabled", True),
            metadata=d.get("metadata", {}),
        )


def load_jobs(jobs_file: Path) -> list[CronJob]:
    """Load cron jobs from a YAML file."""
    if not jobs_file.exists():
        logger.info("No cron jobs file at %s", jobs_file)
        return []

    try:
        with open(jobs_file) as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        logger.error("Failed to load cron jobs from %s: %s", jobs_file, e)
        return []

    jobs_data = data.get("jobs", [])
    if isinstance(data, list):
        jobs_data = data

    jobs = []
    for item in jobs_data:
        try:
            jobs.append(CronJob.from_dict(item))
        except (KeyError, TypeError) as e:
            logger.warning("Invalid cron job definition: %s — %s", item, e)

    logger.info("Loaded %d cron jobs from %s", len(jobs), jobs_file)
    return jobs


def save_jobs(jobs: list[CronJob], jobs_file: Path) -> None:
    """Save cron jobs to a YAML file."""
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    data = {"jobs": []}
    for job in jobs:
        data["jobs"].append({
            "id": job.id,
            "schedule": job.schedule,
            "prompt": job.prompt,
            "description": job.description,
            "model": job.model,
            "session_mode": job.session_mode,
            "context_rotate_hours": job.context_rotate_hours,
            "reminder_mode": job.reminder_mode,
            "enabled": job.enabled,
            "metadata": job.metadata,
        })

    with open(jobs_file, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False)
