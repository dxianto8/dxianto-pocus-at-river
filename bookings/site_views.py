from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .models import EventPackage, RecentEvent


@never_cache
@require_GET
def home(request):
    if request.user.is_authenticated and request.resolver_match.url_name == "home":
        return redirect("accounts:dashboard")
    return render(
        request,
        "home.html",
        {
            "recent_events": RecentEvent.objects.filter(
                is_published=True, event_date__lte=timezone.localdate()
            )[:2],
        },
    )


@require_GET
def packages(request):
    return render(request, "packages.html", {"packages": EventPackage.objects.published()})
