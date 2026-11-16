from .models import Message, VenueSettings


def venue_settings(request):
    context = {"venue": VenueSettings.objects.filter(pk=1).first() or VenueSettings(pk=1)}
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and not request.path.startswith("/admin/"):
        context["unread_messages"] = Message.objects.filter(
            booking__owner=user, from_staff=True, read_at=None
        ).count()
    return context
