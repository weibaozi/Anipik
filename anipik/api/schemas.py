from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class BindingIn(BaseModel):
    source_id: int
    enabled: bool = True
    keywords: list[str] = Field(min_length=1)
    include: list[str] = []
    exclude: list[str] = []


class Metadata(BaseModel):
    bangumi_id: Optional[int] = None
    original_name: Optional[str] = None
    cover_url: Optional[str] = None
    air_date: Optional[str] = None
    total_episodes: Optional[int] = None
    summary: Optional[str] = None


class SubscriptionIn(Metadata):
    name: str = Field(min_length=1)
    enabled: bool = True
    save_dir: Optional[str] = None
    bindings: list[BindingIn] = []      # list order is priority order
    start_episode: Optional[int] = None  # episodes before this are marked skipped


class SubscriptionPatch(Metadata):
    name: Optional[str] = Field(default=None, min_length=1)
    enabled: Optional[bool] = None
    save_dir: Optional[str] = None
    bindings: Optional[list[BindingIn]] = None  # replaces all bindings when given
    move_files: bool = True  # move the existing folder when save_dir changes


class EpisodesPatch(BaseModel):
    numbers: list[int] = Field(min_length=1)
    status: Literal["done", "skipped", "delete"]


class SourceIn(BaseModel):
    name: str = Field(min_length=1)
    kind: str = "rss_search"
    config: dict[str, Any] = {}
    enabled: bool = True


class SourcePatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    config: Optional[dict[str, Any]] = None
    enabled: Optional[bool] = None


class PreviewIn(BaseModel):
    source_id: Optional[int] = None
    kind: str = "rss_search"           # used with config when previewing an unsaved source
    config: Optional[dict[str, Any]] = None
    keywords: list[str] = Field(min_length=1)
    include: list[str] = []
    exclude: list[str] = []
    subscription_id: Optional[int] = None  # annotate releases with that subscription's episode status


class JobAction(BaseModel):
    action: Literal["retry", "retry_from_scratch", "mark_done", "abandon"]
