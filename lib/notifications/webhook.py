import requests as req
from classes.config import Config


def _channels():
    channel = Config().read("notification", "channel", default="webhook", print_error=False) or "webhook"
    return [c.strip().lower() for c in channel.split(",") if c.strip()]


def send_report_to_webhook(data):
    enabled = Config().read("notification", "enabled")
    monthly_enabled = Config().read("notification", "monthly_report_enabled")
    is_monthly = data.get("report_type") == "monthly"

    if enabled == "0":
        return
    if is_monthly and not enabled and monthly_enabled == "0":
        return

    channels = _channels()
    if channels and "webhook" not in channels:
        return

    webhook_url = Config().read("notification", "webhook_url")
    if not webhook_url:
        return

    try:
        response = req.post(webhook_url, json=data, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send report to webhook: {e}")

        # Webhook Operational Fallback to Discord
        discord_webhook_url = Config().read("notification", "discord_webhook_url")
        if discord_webhook_url:
            from lib.notifications.discord import send_notification as send_discord_notification

            site_name = data.get("site") or "unknown"
            event_name = data.get("event") or "backup_event"

            fallback_alert = {
                "report_type": "daily",
                "site": site_name,
                "status": "failed",
                "event": "webhook_failed",
                "title": "⚠️ Webhook Delivery Failed",
                "description": (
                    f"An error occurred while attempting to send notification data to webhook.\n"
                    f"**Webhook URL:** `{webhook_url}`\n"
                    f"**Target Site:** `{site_name}`\n"
                    f"**Event:** `{event_name}`"
                ),
                "message": f"Failed to send report to webhook: {e}",
                "color": 15548997,  # Red
            }
            try:
                send_discord_notification(fallback_alert, force=True)
            except Exception as discord_err:
                print(f"Failed to send Discord fallback alert: {discord_err}")


