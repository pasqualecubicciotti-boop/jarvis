import pytest

from jarvis.config import ConfigError, Settings

BASE = {"TELEGRAM_BOT_TOKEN": "1:FAKE", "TELEGRAM_OWNER_ID": "42", "ANTHROPIC_API_KEY": "sk-FAKE"}


def test_defaults():
    s = Settings.from_env(BASE)
    assert s.model == "claude-haiku-5-5"
    assert s.max_tokens == 1024 and s.daily_limit == 100 and s.owner_id == 42


def test_model_switch():
    assert Settings.from_env({**BASE, "JARVIS_MODEL": "claude-sonnet-5-5"}).model == "claude-sonnet-5-5"


@pytest.mark.parametrize("missing", list(BASE))
def test_missing_required(missing):
    env = {k: v for k, v in BASE.items() if k != missing}
    with pytest.raises(ConfigError):
        Settings.from_env(env)


@pytest.mark.parametrize("extra", [
    {"TELEGRAM_OWNER_ID": "abc"}, {"JARVIS_DAILY_LIMIT": "0"},
    {"JARVIS_MAX_TOKENS": "x"}, {"JARVIS_EFFORT": "max"},
])
def test_invalid_values(extra):
    with pytest.raises(ConfigError):
        Settings.from_env({**BASE, **extra})
