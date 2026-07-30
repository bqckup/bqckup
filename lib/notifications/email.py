from html import escape
from classes.config import Config
from classes.mail import Mail

LOGO_URL = "https://avatars.githubusercontent.com/u/108687982?s=200&v=4"
BRAND_COLOR = "#0A1A4F"   # navy from the Bqckup logo
ACCENT_COLOR = "#F5B820"  # gold from the Bqckup logo

# Map flat payload statuses to Discord-style embed colors
_STATUS_COLORS = {
    "completed": 3066993,            # green
    "no_change": 16776960,           # yellow
    "failed": 15548997,              # red
    "completed_with_errors": 16744192,  # orange
}


def _channels():
    channel = Config().read('notification', 'channel', default='', print_error=False) or ''
    return [c.strip().lower() for c in channel.split(',') if c.strip()]


def _hex_color(color):
    """Convert a Discord-style integer color into a CSS hex string."""
    try:
        return "#{:06X}".format(int(color) & 0xFFFFFF)
    except (TypeError, ValueError):
        return ACCENT_COLOR


def _muted(hex_color):
    """Tone down a bright/neon color by blending it toward a soft slate."""
    h = hex_color.lstrip('#')
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except (ValueError, IndexError):
        return hex_color
    mix = lambda c: int(c * 0.6 + 0x5A * 0.4)
    return "#{:02X}{:02X}{:02X}".format(mix(r), mix(g), mix(b))


def _render_embed(embed):
    accent = _muted(_hex_color(embed.get('color')))
    title = escape(str(embed.get('title') or 'Bqckup Notification'))

    blocks = [
        # Status banner using the embed color
        f"<tr><td style='padding:0'>"
        f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='border-collapse:collapse'>"
        f"<tr><td style='background:{accent};height:6px;line-height:6px;font-size:6px'>&nbsp;</td></tr>"
        f"</table></td></tr>",
        # Title
        f"<tr><td style='padding:28px 32px 0 32px'>"
        f"<h1 style='margin:0;font-size:22px;line-height:1.3;color:#1a1a2e;font-family:Arial,Helvetica,sans-serif'>{title}</h1>"
        f"</td></tr>",
    ]

    description = embed.get('description')
    if description:
        blocks.append(
            f"<tr><td style='padding:12px 32px 0 32px;font-size:14px;line-height:1.6;"
            f"color:#52525b;white-space:pre-line;font-family:Arial,Helvetica,sans-serif'>"
            f"{escape(str(description))}</td></tr>"
        )

    rows = ''
    for field in embed.get('fields') or []:
        name = escape(str(field.get('name') or ''))
        value = escape(str(field.get('value') or ''))
        if not name and not value:
            continue
        rows += (
            "<tr>"
            f"<td style='padding:10px 16px;border-bottom:1px solid #ececf1;font-size:13px;"
            f"font-weight:bold;color:#1a1a2e;white-space:nowrap;vertical-align:top;width:38%'>{name}</td>"
            f"<td style='padding:10px 16px;border-bottom:1px solid #ececf1;font-size:13px;"
            f"color:#3f3f46;white-space:pre-line;word-break:break-word'>{value}</td>"
            "</tr>"
        )
    if rows:
        blocks.append(
            f"<tr><td style='padding:20px 32px 0 32px'>"
            f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
            f"style='border-collapse:collapse;border:1px solid #ececf1;border-radius:8px;overflow:hidden'>"
            f"{rows}</table></td></tr>"
        )

    footer = (embed.get('footer') or {}).get('text')
    if footer:
        blocks.append(
            f"<tr><td style='padding:20px 32px 0 32px;font-size:12px;line-height:1.5;"
            f"color:#a1a1aa;font-family:Arial,Helvetica,sans-serif'>{escape(str(footer))}</td></tr>"
        )

    return ''.join(blocks)


def _render_html(embeds):
    body = ''.join(_render_embed(embed) for embed in embeds)

    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f5f7;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f7;padding:32px 0;">
    <tr><td align="center">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:600px;max-width:600px;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
        <!-- Header / brand -->
        <tr><td style="background:{BRAND_COLOR};padding:22px 32px;">
          <table role="presentation" cellpadding="0" cellspacing="0"><tr>
            <td style="vertical-align:middle;padding-right:12px;">
              <img src="{LOGO_URL}" width="40" height="40" alt="Bqckup" style="display:block;border-radius:10px;background:#ffffff;">
            </td>
            <td style="vertical-align:middle;">
              <span style="font-size:19px;font-weight:bold;color:#ffffff;font-family:Arial,Helvetica,sans-serif;letter-spacing:0.3px;">Bqckup</span>
            </td>
          </tr></table>
        </td></tr>
        <!-- Content -->
        {body}
        <!-- Spacer -->
        <tr><td style="padding:24px 32px 0 32px;"></td></tr>
        <!-- Footer -->
        <tr><td style="padding:20px 32px;border-top:1px solid #ececf1;font-size:12px;line-height:1.5;color:#a1a1aa;font-family:Arial,Helvetica,sans-serif;">
          Sent automatically by <a href="https://bqckup.com" style="color:{BRAND_COLOR};text-decoration:none;font-weight:bold;">Bqckup</a> &middot; Backup and forget!
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _flat_to_embeds(payload):
    """Convert a flat daily notification payload into the embed format
    expected by _render_html. This keeps the existing email template
    working without changes."""
    from datetime import datetime

    status = payload.get("status", "failed")
    color = _STATUS_COLORS.get(status, 15548997)
    timestamp = payload.get("timestamp")
    date_str = (
        datetime.fromtimestamp(timestamp).strftime("%d-%B-%Y %H:%M:%S")
        if timestamp
        else "N/A"
    )

    fields = [
        {"name": "Server IP", "value": payload.get("server_ip", "N/A"), "inline": True},
        {"name": "Site", "value": payload.get("site", "N/A"), "inline": True},
        {"name": "Date", "value": date_str, "inline": True},
        {"name": "Status", "value": status, "inline": True},
    ]

    message = payload.get("message")
    if message:
        fields.append({"name": "Details", "value": message, "inline": False})

    return [{
        "title": payload.get("title", "Bqckup Notification"),
        "description": None,
        "color": color,
        "fields": fields,
        "footer": {"text": None},
    }]


def send_notification(payload):
    if Config().read('notification', 'enabled') != '1':
        return

    if 'email' not in _channels():
        return

    recipient = Config().read('notification', 'email_to')
    if not recipient:
        print("Email notification enabled but `email_to` is not set in bqckup.cnf")
        return

    to = [addr.strip() for addr in recipient.split(',') if addr.strip()]

    try:
        embeds = payload.get('embeds')
        if embeds is None:
            # Flat daily payload — convert to embed format for rendering
            embeds = _flat_to_embeds(payload)
        subject = embeds[0].get('title') if embeds else 'Bqckup Notification'
        Mail().send(subject=subject, to=to, content=_render_html(embeds))
    except Exception as e:
        print(f"Failed to send email notification: {e}")
