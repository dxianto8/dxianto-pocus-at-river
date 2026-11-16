"""Django email backend for SendGrid's v3 API (also used by password resets)."""

import json
from email.utils import getaddresses, parseaddr
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.core.mail.backends.base import BaseEmailBackend


class SendGridBackend(BaseEmailBackend):
    def __init__(self, api_key="", fail_silently=False, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key
        self.fail_silently = fail_silently

    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages:
            if not message.recipients():
                continue
            name, address = parseaddr(message.from_email)
            personalization = {}
            for kind in ("to", "cc", "bcc"):
                recipients = [
                    {"email": email, **({"name": label} if label else {})}
                    for label, email in getaddresses(getattr(message, kind))
                    if email
                ]
                if recipients:
                    personalization[kind] = recipients
            content = [{"type": "text/plain", "value": message.body or " "}]
            for alternative in getattr(message, "alternatives", []):
                if alternative[1] == "text/html":
                    content.append({"type": "text/html", "value": alternative[0]})
            payload = {
                "personalizations": [personalization],
                "from": {"email": address, **({"name": name} if name else {})},
                "subject": message.subject,
                "content": content,
            }
            request = Request(
                "https://api.sendgrid.com/v3/mail/send",
                data=json.dumps(payload).encode(),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urlopen(request, timeout=10) as response:
                    if response.status != 202:
                        raise RuntimeError("SendGrid did not accept the email.")
            except (HTTPError, URLError, RuntimeError):
                if not self.fail_silently:
                    raise
            else:
                sent += 1
        return sent
