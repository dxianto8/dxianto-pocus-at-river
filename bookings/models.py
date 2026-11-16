import os
import uuid
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

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
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="event_bookings",
    )
    package = models.ForeignKey("EventPackage", null=True, blank=True, on_delete=models.SET_NULL)
    package_snapshot = models.CharField(max_length=160, blank=True)
    price_snapshot = models.CharField(max_length=120, blank=True)
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

    @property
    def is_upcoming(self) -> bool:
        return self.event_date >= timezone.localdate()

    @property
    def can_edit(self) -> bool:
        """Customers change a request themselves until the venue has decided on it."""
        return self.status == self.Status.PENDING and self.is_upcoming

    @property
    def can_cancel(self) -> bool:
        return self.status in (self.Status.PENDING, self.Status.CONFIRMED) and self.is_upcoming

    @property
    def days_until(self) -> int:
        return (self.event_date - timezone.localdate()).days

    @property
    def progress(self) -> list[dict]:
        """The steps a request moves through, for the progress line on the event page."""
        s = self.Status
        if self.status in (s.DECLINED, s.CANCELLED):
            return [
                {"label": "Requested", "state": "done"},
                {"label": self.get_status_display(), "state": "stopped"},
            ]
        confirmed = self.status == s.CONFIRMED
        past = not self.is_upcoming
        return [
            {"label": "Requested", "state": "done"},
            {"label": "In review", "state": "done" if confirmed else "current"},
            {"label": "Confirmed", "state": "done" if confirmed else "todo"},
            {
                "label": "Event day",
                "state": "done" if confirmed and past else "current" if confirmed else "todo",
            },
        ]

    @property
    def status_description(self):
        return {
            self.Status.PENDING: "Your date is on hold while the venue team reviews your plans.",
            self.Status.CONFIRMED: "The venue team has confirmed your booking.",
            self.Status.DECLINED: (
                "This request could not be accommodated. You can request another date."
            ),
            self.Status.CANCELLED: "This booking has been cancelled and no longer holds the date.",
        }.get(self.status, "Contact the venue team for details.")


class Activity(models.Model):
    """One line in an event's history, shown to the customer and to staff."""

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="activity")
    text = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name_plural = "activity"

    def __str__(self):
        return self.text


class Message(models.Model):
    """A note between the customer and the venue team about one event."""

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    from_staff = models.BooleanField(default=False, editable=False)
    body = models.TextField(max_length=4000)
    created_at = models.DateTimeField("sent", auto_now_add=True)
    read_at = models.DateTimeField(
        "read", null=True, blank=True, editable=False, help_text="When the other side opened it."
    )

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self):
        return f"{'Venue' if self.from_staff else 'Customer'}: {self.body[:60]}"


class ChecklistItem(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="checklist")
    title = models.CharField(max_length=160)
    due_date = models.DateField("due", null=True, blank=True)
    done_at = models.DateTimeField("done", null=True, blank=True)
    from_staff = models.BooleanField(
        "added by venue", default=False, help_text="Customers can tick these off but not delete."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = [models.F("due_date").asc(nulls_last=True), "pk"]

    def __str__(self):
        return self.title

    @property
    def is_done(self) -> bool:
        return self.done_at is not None

    @property
    def is_overdue(self) -> bool:
        return (
            not self.is_done
            and self.due_date is not None
            and (self.due_date < timezone.localdate())
        )


class ScheduleItem(models.Model):
    """One line of the day-of running order, written by the customer."""

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="schedule")
    time = models.TimeField()
    title = models.CharField("what happens", max_length=160)
    note = models.CharField(max_length=250, blank=True)

    class Meta:
        ordering = ["time", "pk"]

    def __str__(self):
        return f"{self.time:%H:%M} {self.title}"


class Document(models.Model):
    """A file shared on an event. Stored in the database so no file storage is needed."""

    MAX_BYTES = 4 * 1024 * 1024
    ALLOWED_TYPES = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".txt": "text/plain",
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=160)
    filename = models.CharField(max_length=200, editable=False)
    content_type = models.CharField(max_length=120, editable=False)
    size = models.PositiveIntegerField(editable=False, default=0)
    data = models.BinaryField(editable=False)
    from_staff = models.BooleanField(default=False, editable=False)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, editable=False
    )
    seen_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField("added", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @classmethod
    def check_upload(cls, upload) -> str:
        """Return the content type to store for an upload, or raise ValidationError."""
        extension = os.path.splitext(upload.name)[1].lower()
        if extension not in cls.ALLOWED_TYPES:
            raise ValidationError("Upload a PDF, Word, Excel, text, JPG or PNG file.")
        if upload.size > cls.MAX_BYTES:
            raise ValidationError("That file is larger than 4 MB. Upload a smaller one.")
        if upload.size == 0:
            raise ValidationError("That file is empty.")
        return cls.ALLOWED_TYPES[extension]

    def attach(self, upload):
        self.content_type = self.check_upload(upload)
        self.filename = upload.name[-200:]
        self.size = upload.size
        self.data = upload.read()


class CustomerProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    phone = models.CharField(max_length=40, blank=True)
    email_updates = models.BooleanField(
        "Email me about my events",
        default=True,
        help_text="Status changes, new messages and new documents.",
    )

    def __str__(self):
        return f"Profile of {self.user}"


class EventPackage(models.Model):
    class PriceUnit(models.TextChoices):
        EVENT = "event", "per event"
        HOUR = "hour", "per hour"
        PERSON = "person", "per person"

    title = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    event_type = models.CharField(max_length=10, choices=Booking.EventType)
    description = models.TextField(max_length=1000)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="USD. Leave blank to display Request pricing.",
    )
    price_unit = models.CharField(max_length=10, choices=PriceUnit, default=PriceUnit.EVENT)
    starting_at = models.BooleanField(default=True)
    price_note = models.CharField(max_length=250, blank=True)
    inclusions = models.TextField(blank=True, help_text="One confirmed inclusion per line.")
    is_published = models.BooleanField(default=False)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "pk"]

    def __str__(self):
        return self.title

    @property
    def price_display(self):
        if self.price is None:
            return "Request pricing"
        amount = f"{self.price:,.2f}".removesuffix(".00")
        return f"{'From ' if self.starting_at else ''}${amount} {self.get_price_unit_display()}"

    @property
    def inclusion_list(self):
        return [line.strip() for line in self.inclusions.splitlines() if line.strip()]


class VenueSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    name = models.CharField(max_length=100, default="Pocus at River")
    contact_email = models.EmailField(default="events@pocusatriver.com")
    phone = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=200, default="100 S. River Street, Aurora, IL")
    hero_heading = models.CharField(
        max_length=160, default="A place with a story. An event that's yours."
    )
    pricing_intro = models.TextField(
        default=(
            "Start with your occasion. We'll help shape the details around your date, "
            "guest list, and plans."
        )
    )
    pricing_note = models.TextField(
        default=(
            "Final pricing, availability, and inclusions are confirmed in a written proposal. "
            "Submitting a request does not confirm a booking or take a payment."
        )
    )

    class Meta:
        verbose_name = "Venue settings"
        verbose_name_plural = "Venue settings"
        constraints = [models.CheckConstraint(condition=Q(id=1), name="one_venue_settings")]

    def __str__(self):
        return "Venue settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)
