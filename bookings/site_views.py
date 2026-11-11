from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .models import EventPackage


@never_cache
@require_GET
def home(request):
    if request.user.is_authenticated and request.resolver_match.url_name == "home":
        return redirect("accounts:dashboard")
    return render(request, "home.html")


@require_GET
def packages(request):
    return render(
        request, "packages.html", {"packages": EventPackage.objects.filter(is_published=True)}
    )
