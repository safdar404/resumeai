from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

CorrectionStatus = Literal["applied", "pending", "rejected", "accepted"]


class Correction(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:10])
    path: str
    original: str
    corrected: str
    explanation: str
    categories: list[str] = Field(default_factory=list)
    requires_confirmation: bool = False
    status: CorrectionStatus = "applied"
    source: Literal["rules", "llm"] = "rules"

    def signature(self) -> str:
        return f"{self.path}\x1f{self.original}\x1f{self.corrected}"
