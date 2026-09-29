import os
from pathlib import Path

import pytest

FIXTURE_DATA = Path(__file__).parent / "fixtures" / "data"

# Tests never touch the real data dir, never call a paid API and never load the embedding model.
os.environ["DATA_DIR"] = str(FIXTURE_DATA)
os.environ["USE_VECTORS"] = "false"
os.environ["OFFLINE"] = "true"
os.environ.pop("ANTHROPIC_API_KEY", None) if os.environ.get("TARIFFAGENT_LIVE") != "1" else None


@pytest.fixture(autouse=True)
def _fresh_settings(tmp_path, monkeypatch):
    from tariffagent import config

    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


@pytest.fixture
def tools():
    from tariffagent.mcp_server.tools.core import TariffTools

    return TariffTools(use_vectors=False, redact_eval=False)


@pytest.fixture
def redacted_tools():
    from tariffagent.mcp_server.tools.core import TariffTools

    return TariffTools(use_vectors=False, redact_eval=True)
