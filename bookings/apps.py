from django.apps import AppConfig


class BookingsConfig(AppConfig):
    name = "bookings"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        from . import services

        def claim(sender, request, user, **kwargs):
            if request is not None and hasattr(request, "session"):
                services.claim_guest_bookings(request, user)

        user_logged_in.connect(claim, dispatch_uid="claim_guest_bookings", weak=False)
