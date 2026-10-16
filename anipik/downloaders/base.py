"""Downloader contract.

The scheduler calls advance() once per poll for each running job. A downloader keeps its
own progress in `state` (persisted as Job.state) and must call checkpoint() before any
call with side effects, so a crash never leads to a blind resubmission.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable


class TransientError(Exception):
    """Could not reach the backend; the job stays running and is retried next poll."""


class NeedsAttention(Exception):
    """Outcome is uncertain or unsafe to continue automatically; a human must look."""


@dataclass
class JobSpec:
    id: int
    url: str
    destination: str


@dataclass
class Status:
    state: str            # "running" | "done" | "failed"
    progress: float = 0.0  # 0-100
    message: str = ""


class Downloader:
    name = ""
    accepts = frozenset({"magnet"})

    def __init__(self, config: dict):
        self.config = config or {}

    def health(self) -> dict:
        raise NotImplementedError

    @contextmanager
    def connection(self):
        """Opened once per poll around all advance() calls. Raise TransientError if unreachable."""
        yield self

    def advance(self, job: JobSpec, state: dict, checkpoint: Callable[[], None]) -> Status:
        raise NotImplementedError
