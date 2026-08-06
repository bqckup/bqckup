import requests as req
from datetime import datetime
from classes.config import Config
from helpers.datetime import get_today
from helpers.network import get_server_ip

sender = {
    "content": "",
    "username": "Bqckup Notification",
    "avatar_url": "https://avatars.githubusercontent.com/u/108687982?s=48&v=4",
}

# Map flat payload statuses to Discord embed colors
_STATUS_COLORS = {
    "completed": 3066993,            # green
    "no_change": 16776960,           # yellow
    "failed": 15548997,              # red
    "completed_with_errors": 16744192,  # orange
}


def _channels():
    channel = Config().read("notification", "channel", default="", print_error=False) or ""
    return [c.strip().lower() for c in channel.split(",") if c.strip()]


def _flat_to_embed(payload):
    """Convert a flat notification payload into a Discord embed matching the
    exact visual layout (Server IP, Name, Date, additional_data, Details, footer)."""
    server_ip = payload.get("server_ip") or get_server_ip()
    site_name = payload.get("site") or "N/A"

    timestamp = payload.get("timestamp")
    if timestamp:
        date_str = datetime.fromtimestamp(timestamp).strftime("%d-%B-%Y")
    else:
        date_str = get_today(format="%d-%B-%Y")

    fields = [
        {"name": "Server IP", "value": str(server_ip), "inline": True},
        {"name": "Name", "value": str(site_name), "inline": True},
        {"name": "Date", "value": str(date_str), "inline": True},
    ]

    additional_data = payload.get("additional_data")
    if additional_data:
        if isinstance(additional_data, list):
            fields.extend(additional_data)
        else:
            fields.append(additional_data)

    message = payload.get("message")
    if message:
        fields.append({"name": "Details", "value": str(message), "inline": False})

    status = payload.get("status", "failed")
    color = payload.get("color") or _STATUS_COLORS.get(status, 15548997)

    footer_text = payload.get("footer") or "If this was a mistake, please create issue here: https://github.com/bqckup/bqckup"

    embed = {
        "title": payload.get("title", "Bqckup Notification"),
        "description": payload.get("description"),
        "color": color,
        "fields": fields,
        "footer": {"text": footer_text},
    }

    # Clean up empty description if None
    if embed["description"] is None:
        embed.pop("description")

    return [embed]


def send_notification(data, force: bool = False):
    if not force:
        if Config().read("notification", "enabled") != "1":
            return
        if "discord" not in _channels():
            return

    webhook_url = Config().read("notification", "discord_webhook_url")
    if not webhook_url:
        print("Discord notification enabled but `discord_webhook_url` is not set in bqckup.cnf")
        return

    try:
        if "embeds" not in data:
            embeds = _flat_to_embed(data)
            payload = {**sender, "embeds": embeds}
        else:
            payload = {**sender, **data}

        response = req.post(webhook_url, json=payload, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send Discord notification:{e}")
        
        
# if __name__ == "__main__":
    # send_notification({"embeds": [{"title": "Bqckup Failed", "description": "This is an automated notification to inform you that the bqckup has failed.", "color": 15548997, "fields": [{"name": "Server IP", "value": "127.0.0.1", "inline": True}, {"name": "Name", "value": "openjournaltheme.com", "inline": True}, {"name": "Date", "value": "22-03-2024", "inline":True}, {"name": "Details", "value": "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nullam euismod, nisl eget ultricies aliquam, nunc nisl ultricies nunc, nec ultricies nisl nisl nec nisl. Donec euismod, nisl eget ultricies aliquam, nunc nisl ultricies nunc, nec ultricies nisl nisl nec nisl. Donec euismod, nisl eget ultricies aliquam, nunc nisl ultricies nunc, nec ultricies nisl nisl nec nisl. Donec euismod, nisl eget ultricies aliquam, nunc nisl ultricies nunc, nec ultricies nisl nisl nec nisl. Donec euismod, nisl eget ultricies aliquam, nunc nisl ultricies nunc, nec ultricies nisl nisl nec nisl. Donec euismod, nisl eget ultricies aliquam, nunc nisl ultricies nunc, nec ultricies nisl nisl nec nisl. Donec euismod, nisl eget ultricies aliquam, nunc nisl ultricies nunc, nec ultricies nisl nisl nec nisl. Donec euismod, nisl eget ultricies aliquam, nunc nisl ultricies nunc, nec ultricies nisl nisl nec nisl. ", "inline": False}], "footer": {"text": "If this was a mistake, please create issue here: https://github.com/bqckup/bqckup"}}]})