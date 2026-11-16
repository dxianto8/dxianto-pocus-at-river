from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import services
from .models import (
    Booking,
    CateringItem,
    CustomerProfile,
    EventFeedback,
    LoyaltyCredit,
    LoyaltyReward,
    RecentEvent,
    RewardRedemption,
    VenueSettings,
    WalkthroughAppointment,
    WalkthroughSlot,
)


def venue_config():
    return VenueSettings.objects.filter(pk=1).first() or VenueSettings()


@require_GET
def catering(request):
    return render(
        request, "catering.html", {"items": CateringItem.objects.filter(is_published=True)}
    )


@require_GET
def recent_events(request):
    return render(
        request,
        "recent_events.html",
        {
            "events": RecentEvent.objects.filter(
                is_published=True, event_date__lte=timezone.localdate()
            )
        },
    )


class WalkthroughForm(forms.Form):
    slot = forms.ModelChoiceField(queryset=WalkthroughSlot.objects.none(), label="Appointment time")
    notes = forms.CharField(
        required=False,
        max_length=1000,
        label="Anything to know before your visit?",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ""
        taken = WalkthroughAppointment.objects.filter(status__in=["pending", "confirmed"]).values(
            "slot_id"
        )
        self.fields["slot"].queryset = WalkthroughSlot.objects.filter(
            is_published=True, starts_at__gt=timezone.now()
        ).exclude(pk__in=taken)


@never_cache
@require_http_methods(["GET", "POST"])
def walkthroughs(request):
    if request.method == "POST" and not request.user.is_authenticated:
        return redirect(
            reverse("accounts:signup") + "?" + urlencode({"next": reverse("walkthroughs")})
        )
    form = WalkthroughForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                slot = WalkthroughSlot.objects.select_for_update().get(
                    pk=form.cleaned_data["slot"].pk
                )
                if (
                    not slot.is_published
                    or slot.starts_at <= timezone.now()
                    or slot.appointments.filter(status__in=["pending", "confirmed"]).exists()
                ):
                    raise IntegrityError("Slot unavailable")
                appointment = WalkthroughAppointment.objects.create(
                    owner=request.user, slot=slot, notes=form.cleaned_data["notes"]
                )
        except IntegrityError:
            form.add_error("slot", "That appointment was just taken. Choose another time.")
        else:
            services.notify_appointment(appointment, "Walkthrough requested", request)
            messages.success(
                request, "Walkthrough requested. The venue team will confirm your visit."
            )
            return redirect("accounts:walkthroughs")
    return render(
        request,
        "walkthroughs.html",
        {
            "form": form,
            "has_slots": form.fields["slot"].queryset.exists(),
            "appointments": WalkthroughAppointment.objects.filter(
                owner=request.user
            ).select_related("slot")
            if request.user.is_authenticated
            else [],
            "layout_template": "accounts/workspace_base.html"
            if request.user.is_authenticated
            else "base.html",
        },
    )


@never_cache
@login_required
@require_POST
def cancel_walkthrough(request, pk):
    appointment = get_object_or_404(
        WalkthroughAppointment.objects.select_related("slot"), pk=pk, owner=request.user
    )
    if (
        appointment.status in ["pending", "confirmed"]
        and appointment.slot.starts_at > timezone.now()
    ):
        appointment.status = "cancelled"
        appointment.save(update_fields=["status"])
        services.notify_appointment(appointment, "Walkthrough cancelled", request)
        messages.success(request, "Your walkthrough has been cancelled.")
    return redirect("accounts:walkthroughs")


def award_loyalty(user=None):
    venue = venue_config()
    if not venue.loyalty_enabled or not venue.loyalty_points_per_event:
        return
    bookings = Booking.objects.filter(
        owner__isnull=False,
        status="confirmed",
        event_date__gte=venue.loyalty_start_date,
        event_date__lt=timezone.localdate(),
        loyaltycredit__isnull=True,
    )
    if user is not None:
        bookings = bookings.filter(owner=user)
    for booking in bookings:
        LoyaltyCredit.objects.get_or_create(
            booking=booking,
            defaults={
                "owner": booking.owner,
                "points": venue.loyalty_points_per_event,
                "reason": f"Completed event on {booking.event_date:%B %d, %Y}",
            },
        )


def loyalty_balance(user):
    earned = LoyaltyCredit.objects.filter(owner=user).aggregate(total=Sum("points"))["total"] or 0
    used = (
        RewardRedemption.objects.filter(owner=user)
        .exclude(status="declined")
        .aggregate(total=Sum("points"))["total"]
        or 0
    )
    return earned - used


@never_cache
@login_required
@require_GET
def loyalty(request):
    award_loyalty(request.user)
    return render(
        request,
        "accounts/loyalty.html",
        {
            "balance": max(0, loyalty_balance(request.user)),
            "credits": LoyaltyCredit.objects.filter(owner=request.user).order_by("-created_at"),
            "rewards": LoyaltyReward.objects.filter(is_published=True)
            if venue_config().loyalty_enabled
            else [],
            "redemptions": RewardRedemption.objects.filter(owner=request.user).order_by(
                "-created_at"
            ),
        },
    )


@never_cache
@login_required
@require_POST
def redeem_reward(request, pk):
    reward = get_object_or_404(LoyaltyReward, pk=pk, is_published=True)
    if not venue_config().loyalty_enabled:
        messages.info(request, "The loyalty program is not open yet.")
        return redirect("accounts:loyalty")
    award_loyalty(request.user)
    profile = services.profile_for(request.user)
    with transaction.atomic():
        CustomerProfile.objects.select_for_update().get(pk=profile.pk)
        if loyalty_balance(request.user) < reward.points_required:
            messages.error(request, "You do not have enough points for that reward.")
        else:
            RewardRedemption.objects.create(
                owner=request.user,
                reward=reward,
                title_snapshot=reward.title,
                points=reward.points_required,
            )
            messages.success(request, "Reward requested. The team will confirm how to use it.")
    return redirect("accounts:loyalty")


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = EventFeedback
        fields = ["rating", "comments"]
        widgets = {
            "rating": forms.Select(
                choices=[("", "Choose a rating"), *[(n, f"{n} / 5") for n in range(1, 6)]]
            ),
            "comments": forms.Textarea(attrs={"rows": 5}),
        }


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def feedback(request, pk):
    booking = get_object_or_404(
        Booking, pk=pk, owner=request.user, status="confirmed", event_date__lt=timezone.localdate()
    )
    existing = EventFeedback.objects.filter(booking=booking).first()
    form = FeedbackForm(request.POST if request.method == "POST" else None, instance=existing)
    if request.method == "POST" and form.is_valid():
        feedback = form.save(commit=False)
        feedback.booking = booking
        feedback.save()
        messages.success(
            request, "Thank you. Your feedback is shared privately with the venue team."
        )
        return redirect("accounts:feedback", pk=booking.pk)
    return render(
        request,
        "accounts/feedback.html",
        {"form": form, "booking": booking, "submitted": existing is not None},
    )


@never_cache
@login_required
@require_GET
def payments(request):
    return render(request, "accounts/payments.html")
