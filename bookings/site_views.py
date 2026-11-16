from datetime import timedelta

from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .calendar import DayState
from .models import Booking, EventPackage


@never_cache
@require_GET
def home(request):
    if request.user.is_authenticated and request.resolver_match.url_name == "home":
        return redirect("accounts:dashboard")
    return render(request, "home.html", {"saturdays": upcoming_saturdays()})


def upcoming_saturdays(count: int = 8):
    """The next few Saturdays and whether each is free. Only states, never names."""
    today = timezone.localdate()
    first = today + timedelta(days=(5 - today.weekday()) % 7)
    days = [first + timedelta(weeks=n) for n in range(count)]
    taken = Booking.objects.public_states(days[0], days[-1])
    return [{"date": day, "state": taken.get(day, DayState.AVAILABLE)} for day in days]


@require_GET
def packages(request):
    return render(
        request, "packages.html", {"packages": EventPackage.objects.filter(is_published=True)}
    )
