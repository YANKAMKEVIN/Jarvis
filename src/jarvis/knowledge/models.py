from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class SearchMode(Enum):
    GENERAL = "general"
    NEWS = "news"


class TemporalStatus(Enum):
    TODAY = "TODAY"
    YESTERDAY = "YESTERDAY"
    RECENT = "RECENT"
    UNKNOWN = "UNKNOWN"


class SourceType(Enum):
    OFFICIAL = "OFFICIAL"
    REFERENCE = "REFERENCE"
    NEWS = "NEWS"
    OTHER = "OTHER"


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    published_date: str | None = None
    pubdate: str | None = None
    normalized_datetime: datetime | None = None
    temporal_status: TemporalStatus = TemporalStatus.UNKNOWN
    source_type: SourceType = SourceType.OTHER
    engines: list[str] = field(default_factory=list)
    score: float | None = None


@dataclass
class SourceReference:
    title: str
    url: str


@dataclass
class KnowledgeAnswer:
    message: str
    sources: list[SourceReference] = field(default_factory=list)
    requires_external_knowledge: bool = True
    external_knowledge_retrieved: bool = False
    failure_reason: str | None = None
