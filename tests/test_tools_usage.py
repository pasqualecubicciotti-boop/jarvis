from jarvis.tools import build_default_tools
from jarvis.usage import UsageTracker


def test_datetime_and_reminders(tmp_path):
    reg = build_default_tools(tmp_path, "Europe/Rome")
    assert "fuso Europe/Rome" in reg.get("get_datetime").func({})
    assert reg.get("list_reminders").func({}) == "Nessun promemoria salvato."
    reg.get("save_reminder").func({"text": "Chiamare Anna", "when": "domani"})
    out = reg.get("list_reminders").func({})
    assert "Chiamare Anna" in out and "domani" in out
    assert (tmp_path / "reminders.json").exists()


def test_empty_reminder_rejected(tmp_path):
    reg = build_default_tools(tmp_path, "Europe/Rome")
    try:
        reg.get("save_reminder").func({"text": "  "})
    except ValueError:
        return
    raise AssertionError("doveva fallire")


def test_only_forget_needs_confirmation(tmp_path):
    # nessuno strumento che invia/prenota/paga; solo la cancellazione di un appunto chiede il sì/no
    reg = build_default_tools(tmp_path, "Europe/Rome")
    assert {n for n, t in reg._tools.items() if t.requires_confirmation} == {"forget"}


def test_daily_limit_and_errors(tmp_path):
    u = UsageTracker(tmp_path, daily_limit=2)
    assert u.try_consume() and u.try_consume()
    assert not u.try_consume()
    u.record_error("prova")
    assert u.today() == {"requests": 2, "errors": 1}
    # sopravvive al riavvio
    assert UsageTracker(tmp_path, 2).today()["requests"] == 2
