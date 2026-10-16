"""Domain model. A Subscription (one anime) owns its episodes; sources are bound to it.

Episode.status: queued -> downloading -> done | failed | needs_attention
Job.phase:      pending -> running -> done | failed | needs_attention
Job.state holds the downloader's own checkpoint (e.g. PikPak cloud/local sub-phases).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now():
    return datetime.now()


class Base(DeclarativeBase):
    pass


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[object] = mapped_column(JSON)


class Source(Base):
    """A configured source instance, e.g. 'MioBT' of kind 'rss_search'."""
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    kind: Mapped[str] = mapped_column(String)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(default=True)


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    # Relative to library_root unless absolute; defaults to name.
    save_dir: Mapped[Optional[str]] = mapped_column(String)
    # Metadata from bgm.tv (all optional; columns added after the first release must stay nullable).
    bangumi_id: Mapped[Optional[int]]
    original_name: Mapped[Optional[str]] = mapped_column(String)
    cover_url: Mapped[Optional[str]] = mapped_column(String)
    air_date: Mapped[Optional[str]] = mapped_column(String)
    total_episodes: Mapped[Optional[int]]
    summary: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=now)
    updated_at: Mapped[datetime] = mapped_column(default=now, onupdate=now)

    bindings: Mapped[list["SourceBinding"]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan", order_by="SourceBinding.priority")
    episodes: Mapped[list["Episode"]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan", order_by="Episode.number")


class SourceBinding(Base):
    """Per-subscription use of a source; lower priority value is tried first."""
    __tablename__ = "source_bindings"
    __table_args__ = (UniqueConstraint("subscription_id", "source_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"))
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    priority: Mapped[int] = mapped_column(default=0)
    # Source-kind specific, e.g. {"keywords": [...], "include": [...], "exclude": [...]}
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(default=True)

    subscription: Mapped[Subscription] = relationship(back_populates="bindings")
    source: Mapped[Source] = relationship()


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (UniqueConstraint("subscription_id", "number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"))
    number: Mapped[int]
    status: Mapped[str] = mapped_column(String, default="queued")
    attempts: Mapped[int] = mapped_column(default=0)
    release_title: Mapped[Optional[str]] = mapped_column(Text)
    source_name: Mapped[Optional[str]] = mapped_column(String)
    info_hash: Mapped[Optional[str]] = mapped_column(String, index=True)
    updated_at: Mapped[datetime] = mapped_column(default=now, onupdate=now)

    subscription: Mapped[Subscription] = relationship(back_populates="episodes")
    jobs: Mapped[list["Job"]] = relationship(back_populates="episode", order_by="Job.id")


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[Optional[int]] = mapped_column(ForeignKey("episodes.id"))
    downloader: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(Text)
    destination: Mapped[str] = mapped_column(Text)
    phase: Mapped[str] = mapped_column(String, default="pending", index=True)
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    progress: Mapped[float] = mapped_column(default=0.0)
    message: Mapped[Optional[str]] = mapped_column(Text)
    error: Mapped[Optional[str]] = mapped_column(Text)
    transient_errors: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=now)
    updated_at: Mapped[datetime] = mapped_column(default=now, onupdate=now)
    finished_at: Mapped[Optional[datetime]]

    episode: Mapped[Optional[Episode]] = relationship(back_populates="jobs")
