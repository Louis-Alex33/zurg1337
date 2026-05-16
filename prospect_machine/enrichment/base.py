from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class EmailResult:
    email: str = ""
    source: str = ""       # "scrape" | "hunter" | ""
    confidence: float = 0.0  # 0.0–1.0


class EmailFinder(ABC):
    @abstractmethod
    def find(self, domain: str) -> EmailResult:
        raise NotImplementedError
