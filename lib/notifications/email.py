from classes.config import Config
from classes.mail import Mail


def _channels():
    channel = Config().read('notification', 'channel', default='', print_error=False) or ''
    return [c.strip().lower() for c in channel.split(',') if c.strip()]


def _render_html(embeds):
    parts = []
    for embed in embeds:
        title = embed.get('title') or 'Bqckup Notification'
        parts.append(f"<h2 style='margin:0 0 8px'>{title}</h2>")

        description = embed.get('description')
        if description:
            parts.append(f"<p style='white-space:pre-line'>{description}</p>")

        rows = ''
        for field in embed.get('fields') or []:
            name = field.get('name') or ''
            value = field.get('value') or ''
            rows += (
                "<tr>"
                f"<td style='padding:4px 12px 4px 0;font-weight:bold;vertical-align:top'>{name}</td>"
                f"<td style='padding:4px 0;white-space:pre-line'>{value}</td>"
                "</tr>"
            )
        if rows:
            parts.append(f"<table style='border-collapse:collapse'>{rows}</table>")

        footer = (embed.get('footer') or {}).get('text')
        if footer:
            parts.append(f"<p style='color:#888;font-size:12px;margin-top:16px'>{footer}</p>")

    return "<div style='font-family:Arial,sans-serif;color:#222'>" + ''.join(parts) + "</div>"


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
        embeds = payload.get('embeds') or []
        subject = embeds[0].get('title') if embeds else 'Bqckup Notification'
        Mail().send(subject=subject, to=to, content=_render_html(embeds))
    except Exception as e:
        print(f"Failed to send email notification: {e}")
