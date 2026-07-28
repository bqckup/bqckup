import requests as req
from classes.config import Config

def send_report_to_n8n(data):
    webhook_url = Config().read('notification', 'webhook_url')
    if not webhook_url:
        return
    
    response = req.post(webhook_url, json=data, timeout=30)
    response.raise_for_status()
