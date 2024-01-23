import requests as req
from classes.config import Config

sender = {
    "content": "",
    "username" :"Bqckup Notification",
    "avatar_url": "https://avatars.githubusercontent.com/u/108687982?s=48&v=4"
}

def send_notification(data):
    try:
        data = {**sender, **data}
        req.post(Config().read('notification', 'discord_webhook_url'), json=data)        
    except Exception as e:
        print(f"Failed to send notification{e}")
        
        
# if __name__ == "__main__":
    # send_notification({"embeds": [{"title": "Bqckup Failed", "description": "This is an automated notification to inform you that the bqckup has failed.", "color": 15548997, "fields": [{"name": "Server IP", "value": "127.0.0.1", "inline": True}, {"name": "Name", "value": "openjournaltheme.com", "inline": True}, {"name": "Date", "value": "22-03-2024", "inline":True}, {"name": "Details", "value": "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nullam euismod, nisl eget ultricies aliquam, nunc nisl ultricies nunc, nec ultricies nisl nisl nec nisl. Donec euismod, nisl eget ultricies aliquam, nunc nisl ultricies nunc, nec ultricies nisl nisl nec nisl. Donec euismod, nisl eget ultricies aliquam, nunc nisl ultricies nunc, nec ultricies nisl nisl nec nisl. Donec euismod, nisl eget ultricies aliquam, nunc nisl ultricies nunc, nec ultricies nisl nisl nec nisl. Donec euismod, nisl eget ultricies aliquam, nunc nisl ultricies nunc, nec ultricies nisl nisl nec nisl. Donec euismod, nisl eget ultricies aliquam, nunc nisl ultricies nunc, nec ultricies nisl nisl nec nisl. Donec euismod, nisl eget ultricies aliquam, nunc nisl ultricies nunc, nec ultricies nisl nisl nec nisl. Donec euismod, nisl eget ultricies aliquam, nunc nisl ultricies nunc, nec ultricies nisl nisl nec nisl. ", "inline": False}], "footer": {"text": "If this was a mistake, please create issue here: https://github.com/bqckup/bqckup"}}]})