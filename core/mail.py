import smtplib, sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
# from ..helpers.helper import  getAppPath
# sys.path.insert(0, getAppPath())
# sys.path.append("..")
from models import Configuration, MailLog

class Mail(object):
    def __init__(self, data = False):
        self.data = data
        self.status = 1 #success
        self.statusMsg = "Mail sent !"
        self.sendMail = False
        
        if not self.data:
            raise Exception("You need a data to send an email")

        self.setup()

    # desctructor
    def __del__(self):
        if self.sendMail:
            MailLog().create(
                sender=self.mailFrom,
                to=self.target,
                content=self.message,
                status=self.status,
                statusMsg=self.statusMsg
            )

    def setup(self):
        self.target = self.data['target']
        self.subject = self.data['subject']
        self.mailFrom = "OJTBackup"
        self.message = self.data['message']

    def send(self):
        # only send mail if this func running
        self.sendMail = True

        try :
            msg = MIMEMultipart("alternative")
            msg['Subject'] = self.subject
            msg['From'] = self.mailFrom
            msg['To'] = self.target

            # part1 = MIMEText(sel, "plain")
            content = MIMEText(self.message, "html")
            msg.attach(content)

            s = smtplib.SMTP("smtp.gmail.com", 587)
            s.starttls()
            s.login(
                Configuration().generalConfig('email_master'),
                Configuration().generalConfig('password_email_master'),
            )
            s.sendmail(
                self.mailFrom,
                (self.target),
                msg.as_string()
            )
            print("Success send to : %s" % self.target)
        except Exception as e:
            print(f"Error caught reason {e}")
            self.status = 0
            self.statusMsg = e

        
if __name__ == '__main__':
    # pass

    data = {
        'target':'this.nugroho@gmail.com',
        'subject':'Reset your password',
        'message':f"Here's the link to reset your password<br>akdoasdko"
    }
    # x = Mail(data)
    # x.send()
    Mail(data).send()

    # python mail.py