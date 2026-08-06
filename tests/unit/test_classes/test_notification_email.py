"""Unit tests for the email notification channel.

Covers the pure rendering/config logic in ``lib/notifications/email.py`` and the
dispatch from the backup flow (``Bqckup._send_notification``). No real SMTP is
used: ``Config`` and ``Mail`` are mocked, so nothing is actually sent.
"""

from contextlib import contextmanager
from unittest.mock import Mock, patch

import pytest

from lib.notifications.email import (
    ACCENT_COLOR,
    _channels,
    _flat_to_embeds,
    _hex_color,
    _muted,
    _render_html,
    send_notification,
)


@contextmanager
def email_config(**values):
    """Patch Config + Mail for the email module; `values` are config keys."""
    cfg = Mock()
    cfg.read.side_effect = (
        lambda section, key, default=None, print_error=True: values.get(key, default)
    )
    with patch("lib.notifications.email.Config", return_value=cfg), \
         patch("lib.notifications.email.Mail") as MockMail:
        yield MockMail


class TestEmailHelpers:
    def test_channels_parsing(self):
        with email_config(channel="discord, Email "):
            assert _channels() == ["discord", "email"]

    def test_channels_empty(self):
        with email_config(channel=""):
            assert _channels() == []

    def test_hex_color_from_int(self):
        assert _hex_color(0x00FF00) == "#00FF00"

    def test_hex_color_fallback_on_invalid(self):
        assert _hex_color(None) == ACCENT_COLOR
        assert _hex_color("not-a-color") == ACCENT_COLOR

    def test_muted_blends_color(self):
        # mix(0) = int(0*0.6 + 0x5A*0.4) = 0x24
        assert _muted("#000000") == "#242424"

    def test_muted_fallback_on_invalid(self):
        assert _muted("zzz") == "zzz"


class TestRenderHtml:
    def test_contains_title_and_description(self):
        html = _render_html([{"title": "Backup OK", "description": "all good"}])
        assert "Backup OK" in html
        assert "all good" in html

    def test_escapes_html_in_title(self):
        html = _render_html([{"title": "<script>alert(1)</script>"}])
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_escapes_html_in_fields(self):
        html = _render_html([
            {"title": "t", "fields": [{"name": "Host", "value": "<b>x</b>"}]}
        ])
        assert "<b>x</b>" not in html
        assert "&lt;b&gt;x&lt;/b&gt;" in html


class TestSendNotificationGating:
    PAYLOAD = {"embeds": [{"title": "Backup OK", "description": "done"}]}

    def test_not_sent_when_disabled(self):
        with email_config(enabled="0", channel="email", email_to="a@b.com") as MockMail:
            send_notification(self.PAYLOAD)
        MockMail.return_value.send.assert_not_called()

    def test_not_sent_when_channel_excludes_email(self):
        with email_config(enabled="1", channel="discord", email_to="a@b.com") as MockMail:
            send_notification(self.PAYLOAD)
        MockMail.return_value.send.assert_not_called()

    def test_not_sent_when_no_recipient(self):
        with email_config(enabled="1", channel="email", email_to="") as MockMail:
            send_notification(self.PAYLOAD)
        MockMail.return_value.send.assert_not_called()

    def test_sent_when_configured(self):
        with email_config(
            enabled="1", channel="discord,email", email_to="a@b.com, c@d.com"
        ) as MockMail:
            send_notification(self.PAYLOAD)

        MockMail.return_value.send.assert_called_once()
        kwargs = MockMail.return_value.send.call_args.kwargs
        assert kwargs["subject"] == "Backup OK"
        assert kwargs["to"] == ["a@b.com", "c@d.com"]
        assert "Backup OK" in kwargs["content"]


class TestFlatToEmbeds:
    """Test the _flat_to_embeds adapter that converts flat daily payloads to embed format."""

    def test_converts_flat_payload_to_embed(self):
        flat = {
            "report_type": "daily",
            "site": "mysite.com",
            "status": "failed",
            "event": "backup_failed",
            "title": "Backup Failed",
            "message": "Error details",
            "timestamp": 1753836000,
            "server_ip": "1.2.3.4",
        }
        embeds = _flat_to_embeds(flat)
        assert len(embeds) == 1
        assert embeds[0]["title"] == "Backup Failed"
        assert embeds[0]["color"] == 15548997  # red for failed
        field_names = [f["name"] for f in embeds[0]["fields"]]
        assert "Site" in field_names
        assert "Details" in field_names

    def test_omits_details_when_no_message(self):
        flat = {
            "report_type": "daily",
            "site": "mysite.com",
            "status": "completed",
            "event": "test",
            "title": "Test",
            "timestamp": 1753836000,
            "server_ip": "1.2.3.4",
        }
        embeds = _flat_to_embeds(flat)
        field_names = [f["name"] for f in embeds[0]["fields"]]
        assert "Details" not in field_names

    def test_flat_payload_renders_to_html(self):
        """Flat payload should render through the adapter into valid HTML."""
        flat = {
            "report_type": "daily",
            "site": "mysite.com",
            "status": "no_change",
            "event": "no_change_detected",
            "title": "No Changes Detected",
            "message": "Based on file size, no changes.",
            "timestamp": 1753836000,
            "server_ip": "1.2.3.4",
        }
        embeds = _flat_to_embeds(flat)
        html = _render_html(embeds)
        assert "No Changes Detected" in html
        assert "mysite.com" in html

    def test_sent_when_flat_payload(self):
        """send_notification should accept flat payloads (no 'embeds' key)."""
        flat_payload = {
            "report_type": "daily",
            "site": "mysite.com",
            "status": "failed",
            "event": "backup_failed",
            "title": "Backup Failed",
            "message": "Error",
            "timestamp": 1753836000,
            "server_ip": "1.2.3.4",
        }
        with email_config(
            enabled="1", channel="email", email_to="a@b.com"
        ) as MockMail:
            send_notification(flat_payload)

        MockMail.return_value.send.assert_called_once()
        kwargs = MockMail.return_value.send.call_args.kwargs
        assert kwargs["subject"] == "Backup Failed"
        assert "mysite.com" in kwargs["content"]


class TestBackupNotificationDispatch:
    """The backup flow dispatches to webhook, Email, and Discord via _send_notification."""

    def _bqckup(self):
        from classes.bqckup import Bqckup

        # Bypass the heavy __init__ (storage connection checks).
        return Bqckup.__new__(Bqckup)

    @contextmanager
    def _patched(self, already_sent=False):
        with patch("classes.bqckup.get_server_ip", return_value="1.2.3.4"), \
             patch("classes.bqckup.is_debug", return_value=False), \
             patch("classes.bqckup.NotificationLog") as MockNL, \
             patch("classes.bqckup.send_report_to_webhook") as mock_webhook, \
             patch("classes.bqckup.send_email_notification") as mock_email, \
             patch("classes.bqckup.send_discord_notification") as mock_discord:
            (MockNL.return_value.select.return_value
                   .where.return_value.exists.return_value) = already_sent
            yield mock_webhook, mock_email, mock_discord

    def test_dispatches_to_email_webhook_and_discord(self):
        bq = self._bqckup()
        with self._patched(already_sent=False) as (mock_webhook, mock_email, mock_discord):
            bq._send_notification(
                site="mysite", status="failed",
                event="backup_failed", title="Backup Failed",
            )

        mock_webhook.assert_called_once()
        mock_email.assert_called_once()
        mock_discord.assert_called_once()
        payload = mock_webhook.call_args[0][0]
        assert payload["report_type"] == "daily"
        assert payload["site"] == "mysite"
        assert payload["status"] == "failed"
        assert payload["event"] == "backup_failed"
        assert payload["title"] == "Backup Failed"
        assert payload["server_ip"] == "1.2.3.4"

    def test_skips_duplicate_notification(self):
        bq = self._bqckup()
        with self._patched(already_sent=True) as (mock_webhook, mock_email, mock_discord):
            bq._send_notification(
                site="mysite", status="failed",
                event="backup_failed", title="Backup Failed",
            )

        mock_webhook.assert_not_called()
        mock_email.assert_not_called()
        mock_discord.assert_not_called()


@pytest.mark.cli
class TestTestNotificationCommand:
    """The `bqckup test-notification` CLI command sends to Discord AND Email.

    Marked `cli` and excluded from CI: it imports the root `bqckup` module, whose
    importability depends on the full runtime environment.
    """

    @contextmanager
    def _patched(self, enabled="1", channel="discord,email"):
        import bqckup as cli

        cfg = Mock()
        values = {"enabled": enabled, "channel": channel}
        cfg.read.side_effect = (
            lambda section, key, default=None, print_error=True: values.get(key, default)
        )
        with patch("bqckup.Config", return_value=cfg), \
             patch("lib.notifications.discord.send_notification") as mock_discord, \
             patch("lib.notifications.email.send_notification") as mock_email, \
             patch("helpers.network.get_server_ip", return_value="1.2.3.4"), \
             patch("helpers.datetime.get_today", return_value="04-June-2026"):
            yield cli, mock_discord, mock_email

    def test_disabled_sends_nothing(self):
        with self._patched(enabled="0") as (cli, mock_discord, mock_email):
            cli.test_notification()
        mock_discord.assert_not_called()
        mock_email.assert_not_called()

    def test_no_channel_sends_nothing(self):
        with self._patched(enabled="1", channel="") as (cli, mock_discord, mock_email):
            cli.test_notification()
        mock_discord.assert_not_called()
        mock_email.assert_not_called()

    def test_sends_to_discord_and_email(self):
        with self._patched(enabled="1", channel="discord,email") as (cli, mock_discord, mock_email):
            cli.test_notification()

        mock_discord.assert_called_once()
        mock_email.assert_called_once()
        payload = mock_email.call_args[0][0]
        assert payload["embeds"][0]["title"] == "Bqckup Test Notification"
