from django.shortcuts import render
from django.views.decorators.http import require_GET

from .models import EventPackage


@require_GET
def home(request):
    return render(request, "home.html")


@require_GET
def packages(request):
    return render(
        request, "packages.html", {"packages": EventPackage.objects.filter(is_published=True)}
    )
