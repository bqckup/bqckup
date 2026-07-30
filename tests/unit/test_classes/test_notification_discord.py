"""Unit tests for Discord notification channel and webhook fallback alert."""

from contextlib import contextmanager
from unittest.mock import Mock, patch

import pytest

from lib.notifications.discord import (
    _STATUS_COLORS,
    _channels,
    _flat_to_embed,
    send_notification as send_discord_notification,
)
from lib.notifications.webhook import send_report_to_webhook


@contextmanager
def discord_config(**values):
    """Patch Config for the discord module; `values` are config keys."""
    cfg = Mock()
    cfg.read.side_effect = (
        lambda section, key, default=None, print_error=True: values.get(key, default)
    )
    with patch("lib.notifications.discord.Config", return_value=cfg), \
         patch("lib.notifications.discord.req.post") as mock_post:
        yield mock_post


@contextmanager
def webhook_config(**values):
    """Patch Config for the webhook module; `values` are config keys."""
    cfg = Mock()
    cfg.read.side_effect = (
        lambda section, key, default=None, print_error=True: values.get(key, default)
    )
    with patch("lib.notifications.webhook.Config", return_value=cfg), \
         patch("lib.notifications.webhook.req.post") as mock_post:
        yield mock_post


class TestDiscordAdapter:
    def test_flat_payload_conversion(self):
        flat = {
            "report_type": "daily",
            "site": "test3",
            "status": "no_change",
            "event": "no_change_detected",
            "title": "No Changes Detected",
            "description": "We have not detected any changes.",
            "message": "Based on file size, there is no changes detected",
            "additional_data": {"name": "File name", "value": "123.tar.gz", "inline": False},
            "footer": "Custom footer text",
            "timestamp": 1753836000,
            "server_ip": "182.253.53.67",
        }
        embeds = _flat_to_embed(flat)
        assert len(embeds) == 1
        embed = embeds[0]

        assert embed["title"] == "No Changes Detected"
        assert embed["description"] == "We have not detected any changes."
        assert embed["color"] == 16776960  # yellow for no_change
        assert embed["footer"]["text"] == "Custom footer text"

        field_names = [f["name"] for f in embed["fields"]]
        assert "Server IP" in field_names
        assert "Name" in field_names
        assert "Date" in field_names
        assert "File name" in field_names
        assert "Details" in field_names

    def test_default_status_colors(self):
        for status, color in _STATUS_COLORS.items():
            flat = {"status": status, "site": "s"}
            embeds = _flat_to_embed(flat)
            assert embeds[0]["color"] == color


class TestDiscordSendNotificationGating:
    FLAT_PAYLOAD = {
        "report_type": "daily",
        "site": "test",
        "status": "failed",
        "event": "test_event",
        "title": "Test Title",
    }

    def test_not_sent_when_disabled(self):
        with discord_config(enabled="0", channel="discord", discord_webhook_url="https://discord.com/hook") as mock_post:
            send_discord_notification(self.FLAT_PAYLOAD)
        mock_post.assert_not_called()

    def test_not_sent_when_channel_excludes_discord(self):
        with discord_config(enabled="1", channel="webhook", discord_webhook_url="https://discord.com/hook") as mock_post:
            send_discord_notification(self.FLAT_PAYLOAD)
        mock_post.assert_not_called()

    def test_not_sent_when_missing_webhook_url(self):
        with discord_config(enabled="1", channel="discord", discord_webhook_url="") as mock_post:
            send_discord_notification(self.FLAT_PAYLOAD)
        mock_post.assert_not_called()

    def test_sent_when_configured(self):
        with discord_config(enabled="1", channel="discord,webhook", discord_webhook_url="https://discord.com/hook") as mock_post:
            send_discord_notification(self.FLAT_PAYLOAD)
        mock_post.assert_called_once()
        kwargs = mock_post.call_args.kwargs
        assert kwargs["json"]["embeds"][0]["title"] == "Test Title"

    def test_force_bypasses_channel_and_enabled_gating(self):
        with discord_config(enabled="0", channel="", discord_webhook_url="https://discord.com/hook") as mock_post:
            send_discord_notification(self.FLAT_PAYLOAD, force=True)
        mock_post.assert_called_once()


class TestWebhookFallbackToDiscord:
    PAYLOAD = {
        "report_type": "daily",
        "site": "mysite",
        "status": "failed",
        "event": "backup_failed",
        "title": "Backup Failed",
    }

    def test_webhook_failure_triggers_discord_fallback(self):
        with webhook_config(
            enabled="1",
            channel="webhook",
            webhook_url="https://invalid-webhook.com/hook",
            discord_webhook_url="https://discord.com/hook",
        ) as mock_post, \
             patch("lib.notifications.discord.send_notification") as mock_discord_send:
            # Simulate HTTP failure on webhook
            mock_post.return_value.raise_for_status.side_effect = Exception("404 Client Error")

            send_report_to_webhook(self.PAYLOAD)

        mock_discord_send.assert_called_once()
        call_kwargs = mock_discord_send.call_args
        fallback_data = call_kwargs[0][0]
        force_flag = call_kwargs[1].get("force")

        assert force_flag is True
        assert fallback_data["title"] == "⚠️ Webhook Delivery Failed"
        assert fallback_data["event"] == "webhook_failed"
