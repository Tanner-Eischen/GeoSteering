from unittest.mock import Mock

from app.ui import navigation


def test_navigation_resets_scroll_but_same_page_edits_do_not(monkeypatch):
    session = {}
    emit = Mock()
    monkeypatch.setattr(navigation.st, "session_state", session)
    monkeypatch.setattr(navigation.st, "html", emit)
    navigation.reset_scroll_on_navigation("Correlation Panel", "project-a")
    first_script = emit.call_args.args[0]
    navigation.reset_scroll_on_navigation("Correlation Panel", "project-a")
    assert emit.call_count == 1
    navigation.reset_scroll_on_navigation("Steering Console", "project-a")
    assert emit.call_count == 2
    assert emit.call_args.args[0] != first_script
    navigation.reset_scroll_on_navigation("Steering Console", "project-b")
    assert emit.call_count == 3
    assert session["_page_navigation_revision"] == 3


def test_navigation_script_does_not_include_user_content(monkeypatch):
    emit = Mock()
    monkeypatch.setattr(navigation.st, "session_state", {})
    monkeypatch.setattr(navigation.st, "html", emit)
    navigation.reset_scroll_on_navigation("Dashboard", '</script><script>alert("user data")</script>')
    assert "user data" not in emit.call_args.args[0]
