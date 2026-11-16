from django.core.management.base import BaseCommand

from bookings.notifications import dispatch_notifications


class Command(BaseCommand):
    help = "Deliver due opt-in event/walkthrough reminders and post-event feedback invitations."

    def handle(self, *args, **options):
        result = dispatch_notifications()
        self.stdout.write(
            f"Sent: {result['sent']}; failed: {result['failed']}; skipped: {result['skipped']}"
        )
