from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from bookings.models import Booking

from .forms import RegistrationForm


def safe_next(request):
    value = request.POST.get("next") or request.GET.get("next", "")
    return (
        value
        if url_has_allowed_host_and_scheme(
            value, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        )
        else ""
    )


@never_cache
@require_http_methods(["GET", "POST"])
def signup(request):
    destination = safe_next(request)
    if request.user.is_authenticated:
        return redirect(destination or "accounts:dashboard")
    form = RegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = form.save()
        except IntegrityError:
            form.add_error("username", "That username is unavailable. Please choose another.")
        else:
            login(request, user)
            return redirect(destination or "accounts:dashboard")
    return render(request, "accounts/signup.html", {"form": form, "next": destination})


@never_cache
@login_required
@require_GET
def dashboard(request):
    bookings = (
        Booking.objects.filter(owner=request.user).select_related("package").order_by("-created_at")
    )
    return render(request, "accounts/dashboard.html", {"bookings": bookings})


@never_cache
@login_required
@require_GET
def booking_detail(request, pk):
    booking = get_object_or_404(Booking, pk=pk, owner=request.user)
    return render(request, "accounts/booking_detail.html", {"booking": booking})
