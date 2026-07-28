import requests as req
from classes.config import Config

def send_report_to_webhook(data):
    webhook_url = Config().read('notification', 'webhook_url')
    if not webhook_url:
        return
    
    try:
        response = req.post(webhook_url, json=data, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send report to webhook: {e}")
