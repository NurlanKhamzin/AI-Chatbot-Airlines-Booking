from unittest.mock import MagicMock, patch

import backend.mailer as mailer_mod
from backend.mailer import _send_sync, smtp_configured


class _SmtpOk:
    smtp_host = "127.0.0.1"
    smtp_port = 1025
    smtp_from = "noreply@test.local"
    smtp_user = ""
    smtp_password = ""
    smtp_use_tls = False
    smtp_ssl = False


class _SmtpEmpty:
    smtp_host = ""
    smtp_from = ""


def test_smtp_configured_true_and_false(monkeypatch):
    monkeypatch.setattr(mailer_mod, "settings", _SmtpOk())
    assert smtp_configured() is True
    monkeypatch.setattr(mailer_mod, "settings", _SmtpEmpty())
    assert smtp_configured() is False


@patch("backend.mailer.smtplib.SMTP")
def test_send_sync_success(mock_smtp_class, monkeypatch):
    monkeypatch.setattr(mailer_mod, "settings", _SmtpOk())
    server = MagicMock()
    ctx = MagicMock()
    ctx.__enter__.return_value = server
    ctx.__exit__.return_value = None
    mock_smtp_class.return_value = ctx

    err = _send_sync("user@test.local", "Flight booking — ABC", "Plain body")
    assert err == ""
    server.send_message.assert_called_once()
