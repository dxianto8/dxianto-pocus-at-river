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
