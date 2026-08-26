"""Model fallback chain tests — no real API calls, just resolution logic."""
import importlib
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _reload_config(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import app.config as config

    importlib.reload(config)
    return config


@pytest.fixture()
def fresh_models(monkeypatch):
    """Reload config + model modules with the given env each time."""
    def _do(**env):
        cfg = _reload_config(monkeypatch, **env)
        import app.models.groq_model as groq_model
        import app.models.gemini_model as gemini_model

        importlib.reload(groq_model)
        importlib.reload(gemini_model)
        return groq_model, gemini_model
    return _do


def test_groq_preferred_when_set(fresh_models, monkeypatch):
    gm, _ = fresh_models(GROQ_API_KEY="g", GOOGLE_API_KEY="", OPENROUTER_API_KEY="o")
    m = gm.get_groq_llama()
    assert "groq" in str(getattr(m, "base_url", ""))


def test_gemini_fallback_without_groq(fresh_models, monkeypatch):
    gm, _ = fresh_models(GROQ_API_KEY="", GOOGLE_API_KEY="gkey", OPENROUTER_API_KEY="")
    m = gm.get_groq_llama()
    # Agno Gemini model carries the id we set
    assert getattr(m, "id", "") == "gemini-3.6-flash"


def test_openrouter_final_fallback(fresh_models, monkeypatch):
    gm, _ = fresh_models(
        GROQ_API_KEY="", GOOGLE_API_KEY="", OPENROUTER_API_KEY="okey"
    )
    m = gm.get_groq_llama()
    assert "openrouter" in str(getattr(m, "base_url", ""))
    assert "minimax" in str(getattr(m, "id", ""))


def test_no_keys_raises(fresh_models, monkeypatch):
    gm, _ = fresh_models(GROQ_API_KEY="", GOOGLE_API_KEY="", OPENROUTER_API_KEY="")
    with pytest.raises(ValueError, match="No LLM key set"):
        gm.get_groq_llama()


def test_gemini_helpers_openrouter_fallback(fresh_models, monkeypatch):
    _, gem = fresh_models(GOOGLE_API_KEY="", OPENROUTER_API_KEY="okey")
    m = gem.get_gemini_flash()
    assert "openrouter" in str(getattr(m, "base_url", ""))


def test_mistral_chain_openrouter_before_gemini(fresh_models, monkeypatch):
    gm, _ = fresh_models(MISTRAL_API_KEY="", GOOGLE_API_KEY="g", OPENROUTER_API_KEY="o")
    m = gm.get_mistral_large()
    assert "openrouter" in str(getattr(m, "base_url", ""))


@pytest.fixture(scope="session", autouse=True)
def restore_config():
    """After fallback-mangling env/modules, reload once more with real .env."""
    yield
    import app.config as config
    import app.models.groq_model as groq_model
    import app.models.gemini_model as gemini_model

    importlib.reload(config)
    importlib.reload(groq_model)
    importlib.reload(gemini_model)
