import requests as req
from classes.config import Config

sender = {
    "content": "",
    "username": "Bqckup Notification",
    "avatar_url": "https://avatars.githubusercontent.com/u/108687982?s=48&v=4"
}

def send_report_to_webhook(data):
    webhook_url = Config().read('notification', 'webhook_url')
    if not webhook_url:
        return
    
    try:
        response = req.post(webhook_url, json={**sender, **data}, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send report to webhook: {e}")
