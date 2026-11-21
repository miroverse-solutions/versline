from versline.core.constants import DEFAULT_MAX_RETRIES, MAX_RETRIES_ENV, configured_max_retries


def test_default_when_unset(monkeypatch):
    monkeypatch.delenv(MAX_RETRIES_ENV, raising=False)
    assert configured_max_retries() == DEFAULT_MAX_RETRIES


def test_reads_and_clamps_env(monkeypatch):
    monkeypatch.setenv(MAX_RETRIES_ENV, "5")
    assert configured_max_retries() == 5
    monkeypatch.setenv(MAX_RETRIES_ENV, "0")
    assert configured_max_retries() == 1
    monkeypatch.setenv(MAX_RETRIES_ENV, "99")
    assert configured_max_retries() == 10
    monkeypatch.setenv(MAX_RETRIES_ENV, "abc")
    assert configured_max_retries() == DEFAULT_MAX_RETRIES
