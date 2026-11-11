from .models import VenueSettings


def venue_settings(request):
    return {"venue": VenueSettings.objects.filter(pk=1).first() or VenueSettings(pk=1)}
