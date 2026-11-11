import uuid
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from .calendar import DayState


class BookingQuerySet(models.QuerySet):
    def active(self):
        """Bookings that hold their date: pending requests, confirmed bookings and blocks."""
        return self.filter(status__in=Booking.ACTIVE_STATUSES)

    def public_states(self, start: date, end: date) -> dict[date, DayState]:
        """What visitors may see for each taken date in a range. Never includes personal details."""
        rows = (
            self.active().filter(event_date__range=(start, end)).values_list("event_date", "status")
        )
        return {
            day: DayState.ON_HOLD if status == Booking.Status.PENDING else DayState.BOOKED
            for day, status in rows
        }


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        DECLINED = "declined", "Declined"
        CANCELLED = "cancelled", "Cancelled"
        BLOCKED = "blocked", "Blocked by venue"

    class EventType(models.TextChoices):
        WEDDING = "wedding", "Wedding"
        CORPORATE = "corporate", "Corporate event"
        OTHER = "other", "Other"

    ACTIVE_STATUSES = (Status.PENDING, Status.CONFIRMED, Status.BLOCKED)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_date = models.DateField("event date")
    status = models.CharField(max_length=10, choices=Status, default=Status.PENDING)

    name = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    event_type = models.CharField("event type", max_length=10, choices=EventType, blank=True)
    guest_count = models.PositiveSmallIntegerField(
        "guests",
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(settings.BOOKING_MAX_GUESTS)],
    )
    message = models.TextField(blank=True)
    admin_note = models.TextField(
        "admin note", blank=True, help_text="Only visible here in the admin."
    )

    created_at = models.DateTimeField("received", auto_now_add=True)
    updated_at = models.DateTimeField("last changed", auto_now=True)

    objects = BookingQuerySet.as_manager()

    class Meta:
        ordering = ["event_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["event_date"],
                condition=Q(status__in=["pending", "confirmed", "blocked"]),
                name="one_active_booking_per_date",
                violation_error_message="That date already has an active booking.",
            )
        ]

    def __str__(self) -> str:
        who = self.name or self.get_status_display()
        return f"{self.event_date:%a %d %b %Y}: {who}"

    @property
    def is_active(self) -> bool:
        return self.status in self.ACTIVE_STATUSES

    def clean(self):
        super().clean()
        if self.status == self.Status.BLOCKED:
            return
        required = {
            "name": self.name,
            "email": self.email,
            "event_type": self.event_type,
            "guest_count": self.guest_count,
        }
        missing = {
            field: "Required for bookings."
            for field, value in required.items()
            if value in ("", None)
        }
        if missing:
            raise ValidationError(missing)


class WalkthroughRequest(models.Model):
    """A preferred visit time, never a hold on the event calendar."""

    class TimeWindow(models.TextChoices):
        FLEXIBLE = "flexible", "I'm flexible"
        MORNING = "morning", "Morning"
        AFTERNOON = "afternoon", "Afternoon"
        EVENING = "evening", "Evening"

    class Status(models.TextChoices):
        PENDING = "pending", "New request"
        CONTACTED = "contacted", "Contacted"
        CONFIRMED = "confirmed", "Visit confirmed"
        CANCELLED = "cancelled", "Cancelled"

    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    preferred_date = models.DateField()
    preferred_time = models.CharField(max_length=12, choices=TimeWindow)
    event_type = models.CharField(max_length=10, choices=Booking.EventType, blank=True)
    message = models.TextField(blank=True, max_length=2000)
    status = models.CharField(max_length=12, choices=Status, default=Status.PENDING)
    contact_consent_at = models.DateTimeField(editable=False)
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} — {self.preferred_date:%b %d, %Y}"


class Testimonial(models.Model):
    quote = models.TextField(max_length=800, help_text="Use the guest's approved words.")
    attribution = models.CharField(max_length=120, help_text="Public name approved by the guest.")
    event_label = models.CharField(max_length=120, blank=True)
    source_url = models.URLField(blank=True, help_text="Optional link to the original review.")
    permission_granted = models.BooleanField(
        default=False, help_text="The guest has given permission to publish this quote and name."
    )
    is_published = models.BooleanField(default=False)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "pk"]

    def __str__(self):
        return self.attribution

    def clean(self):
        super().clean()
        if self.is_published and not self.permission_granted:
            raise ValidationError(
                {"permission_granted": "Get the guest's permission before publishing."}
            )
