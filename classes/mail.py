from classes.config import Config

class MailExceptoin(Exception):
    pass

class Mail:
    def __init__(self):
        self.email = Config().read('email', 'email')
        self.name = Config().read('email', 'name')
        self.password = Config().read('email', 'password')
        self.host = Config().read('email', 'host')
        self.encryption = Config().read('email', 'encryption')
        self.port = Config().read('email', 'port')

    def send(self, subject: str, to: list, content: str):
        try:
            import emails
            message = emails.html(html=content, subject=subject, mail_from=(self.name, self.email))
            encryption = (self.encryption or '').lower()
            smtp = {
                'host': self.host,
                'port': int(self.port) if self.port else 25,
                'tls': encryption == 'tls',
                'ssl': encryption == 'ssl',
            }
            # only authenticate when a password is set; local test servers (Mailpit/Mailhog) need no auth
            if self.password:
                smtp['user'] = self.email
                smtp['password'] = self.password

            response = message.send(to=to, smtp=smtp)
            if response is None or not response.success:
                raise MailExceptoin(f"SMTP delivery failed: {getattr(response, 'error', response)}")
        except Exception as e:
            raise MailExceptoin(str(e))