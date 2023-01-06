from classes.config import Config

class MailExceptoin(Exception):
    pass

class Mail:
    def __init__(self):
        self.email = Config().read('email', 'email')
        self.name = Config().read('email', 'name')
        self.password = Config().read('email', 'password')
        self.mailer = Config().read('email', 'mailer')
        self.host = Config().read('email', 'host')
        self.encryption = Config().read('email', 'encryption')
        self.port = Config().read('email', 'port')

    def send(self, subject: str, to: list, content: str):
        try:
            import jinja2, emails
            message = emails.html(html=content, subject=subject, mail_from=(self.name, self.email))
            smtp={
                'host': self.host,
                'port': self.port,
                'user': self.email,
                'password': self.password,
                'tls': self.encryption.lower() == 'tls',
            }
            message.send(
                to=to,
                smtp=smtp,
            )
        except Exception as e:
            raise MailExceptoin(str(e))