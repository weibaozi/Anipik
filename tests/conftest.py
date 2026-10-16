import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anipik.db import make_session_factory  # noqa: E402


@pytest.fixture
def factory(tmp_path):
    return make_session_factory(tmp_path / "test.db")
