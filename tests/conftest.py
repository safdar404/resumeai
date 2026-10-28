import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from src.models.profile import CandidateProfile  # noqa: E402

EX = ROOT / "examples"


@pytest.fixture
def gis_profile() -> CandidateProfile:
    return CandidateProfile.model_validate_json((EX / "sample_profile_gis.json").read_text(encoding="utf-8"))


@pytest.fixture
def gis_job() -> str:
    return (EX / "job_gis_analyst.txt").read_text(encoding="utf-8")
