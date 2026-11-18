import app as app_module


def test_moderator_access_accepts_exact_configured_email(monkeypatch):
    monkeypatch.setenv("ONECRE8_MODERATOR_USER_IDS", "")
    monkeypatch.setenv("ONECRE8_MODERATOR_EMAILS", "heavenonearth245@gmail.com")
    assert app_module.is_onecre8_moderator(42, "heavenonearth245@gmail.com")


def test_moderator_email_matching_is_case_insensitive_and_trimmed(monkeypatch):
    monkeypatch.setenv("ONECRE8_MODERATOR_USER_IDS", "")
    monkeypatch.setenv("ONECRE8_MODERATOR_EMAILS", "  HeavenOnEarth245@Gmail.com  ")
    assert app_module.is_onecre8_moderator(42, "heavenonearth245@gmail.com")


def test_moderator_email_must_match_exactly(monkeypatch):
    monkeypatch.setenv("ONECRE8_MODERATOR_USER_IDS", "")
    monkeypatch.setenv("ONECRE8_MODERATOR_EMAILS", "heavenonearth245@gmail.com")
    assert not app_module.is_onecre8_moderator(42, "other@gmail.com")
    assert not app_module.is_onecre8_moderator(42, "heavenonearth245+other@gmail.com")
    assert not app_module.is_onecre8_moderator(42, "")


def test_existing_numeric_moderator_allowlist_remains_supported(monkeypatch):
    monkeypatch.setenv("ONECRE8_MODERATOR_USER_IDS", "7, 42")
    monkeypatch.setenv("ONECRE8_MODERATOR_EMAILS", "")
    assert app_module.is_onecre8_moderator(42, "someone@example.com")
    assert not app_module.is_onecre8_moderator(99, "someone@example.com")
