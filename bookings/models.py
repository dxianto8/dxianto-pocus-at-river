import os
import uuid
from datetime import date, time
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .calendar import DayState

NOON = time(12)


# Which halves of the day each session holds. A full day holds both, so it collides with either.
HALVES = {"full": ("am", "pm"), "am": ("am",), "pm": ("pm",)}


class BookingQuerySet(models.QuerySet):
    def active(self):
        """Bookings that hold their date: pending requests, confirmed bookings and blocks."""
        return self.filter(status__in=Booking.ACTIVE_STATUSES)

    def taken_halves(self, start: date, end: date, exclude_pk=None) -> dict[date, dict[str, str]]:
        """For each date with an active booking: {half: status} for the halves it holds."""
        rows = self.active().filter(event_date__range=(start, end))
        if exclude_pk is not None:
            rows = rows.exclude(pk=exclude_pk)
        taken: dict[date, dict[str, str]] = {}
        for day, session, status in rows.values_list("event_date", "session", "status"):
            for half in HALVES.get(session, HALVES["full"]):
                taken.setdefault(day, {})[half] = status
        return taken

    def open_sessions(self, day: date, exclude_pk=None) -> list[str]:
        """The sessions that can still be requested on a date, in display order."""
        held = self.taken_halves(day, day, exclude_pk).get(day, {})
        return [
            session
            for session in Booking.Session.values
            if not any(half in held for half in HALVES[session])
        ]

    def public_halves(self, start: date, end: date) -> dict[date, dict[str, str]]:
        """What visitors may see for each half of each taken date: "on_hold" or "booked"."""
        return {
            day: {
                half: "on_hold" if status == Booking.Status.PENDING else "booked"
                for half, status in held.items()
            }
            for day, held in self.taken_halves(start, end).items()
        }

    def public_states(self, start: date, end: date) -> dict[date, DayState]:
        """What visitors may see for each taken date in a range. Never includes personal details."""
        states = {}
        for day, held in self.taken_halves(start, end).items():
            if "am" not in held:
                states[day] = DayState.AM_OPEN
            elif "pm" not in held:
                states[day] = DayState.PM_OPEN
            elif Booking.Status.PENDING in held.values():
                states[day] = DayState.ON_HOLD
            else:
                states[day] = DayState.BOOKED
        return states


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

    class Session(models.TextChoices):
        FULL = "full", "Full day"
        AM = "am", "AM"
        PM = "pm", "PM"

    ACTIVE_STATUSES = (Status.PENDING, Status.CONFIRMED, Status.BLOCKED)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_date = models.DateField("event date")
    session = models.CharField(
        "time of day",
        max_length=4,
        choices=Session,
        default=Session.FULL,
        help_text="AM and PM bookings can share a date; a full day holds both.",
    )
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
    event_type = models.CharField("event type", max_length=40, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    catering_interest = models.BooleanField(default=False)
    dietary_notes = models.TextField(max_length=1000, blank=True)
    questionnaire_answers = models.JSONField(default=list, blank=True)
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
        # One index per half of the day: a full day sits in both, AM and PM in one each.
        constraints = [
            models.UniqueConstraint(
                fields=["event_date"],
                condition=Q(
                    status__in=["pending", "confirmed", "blocked"], session__in=["full", "am"]
                ),
                name="one_active_am_booking_per_date",
                violation_error_message="The morning of that date already has an active booking.",
            ),
            models.UniqueConstraint(
                fields=["event_date"],
                condition=Q(
                    status__in=["pending", "confirmed", "blocked"], session__in=["full", "pm"]
                ),
                name="one_active_pm_booking_per_date",
                violation_error_message=(
                    "The afternoon of that date already has an active booking."
                ),
            ),
        ]

    def __str__(self) -> str:
        who = self.name or self.get_status_display()
        return f"{self.event_date:%a %d %b %Y} ({self.get_session_display()}): {who}"

    @property
    def when(self) -> str:
        """The date and time of day, for headings and emails: "Saturday, June 5, 2027 · PM"."""
        return f"{self.event_date:%A, %B %-d, %Y} · {self.get_session_display()}"

    def get_event_type_display(self):
        option = EventTypeOption.objects.filter(code=self.event_type).first()
        return (
            option.label
            if option
            else dict(self.EventType.choices).get(self.event_type, self.event_type)
        )

    @property
    def is_active(self) -> bool:
        return self.status in self.ACTIVE_STATUSES

    def clean(self):
        super().clean()
        if self.status == self.Status.BLOCKED:
            return
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError(
                {"end_time": "End time must be after start time on the same day."}
            )
        if self.start_time and self.session == self.Session.AM and self.start_time >= NOON:
            raise ValidationError({"start_time": "An AM booking starts before noon."})
        if self.start_time and self.session == self.Session.PM and self.start_time < NOON:
            raise ValidationError({"start_time": "A PM booking starts at noon or later."})
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
    def is_completed(self) -> bool:
        """A confirmed event whose day has passed."""
        return self.status == self.Status.CONFIRMED and not self.is_upcoming

    @property
    def display_status(self) -> tuple[str, str]:
        """(key, label) for the status chip: past confirmed events read as Completed."""
        if self.is_completed:
            return "completed", "Completed"
        return self.status, self.get_status_display()

    @property
    def status_description(self):
        if self.is_completed:
            return "This event has taken place. Thank you for celebrating with us."
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

    sms_reminders = models.BooleanField("Text me event and walkthrough reminders", default=False)
    feedback_updates = models.BooleanField(
        "Invite me to share feedback after an event", default=False
    )

    def __str__(self):
        return f"Profile of {self.user}"


class EventPackageQuerySet(models.QuerySet):
    def published(self):
        packages = self.filter(is_published=True)
        if EventTypeOption.objects.exists():
            packages = packages.filter(
                event_type__in=EventTypeOption.objects.filter(is_active=True).values("code")
            )
        return packages


class EventPackage(models.Model):
    class PriceUnit(models.TextChoices):
        EVENT = "event", "per event"
        HOUR = "hour", "per hour"
        PERSON = "person", "per person"

    title = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    event_type = models.CharField(max_length=40)
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

    objects = EventPackageQuerySet.as_manager()

    class Meta:
        ordering = ["display_order", "pk"]

    def __str__(self):
        return self.title

    def get_event_type_display(self):
        option = EventTypeOption.objects.filter(code=self.event_type).first()
        return option.label if option else self.event_type

    @property
    def current_offer(self):
        today = timezone.localdate()
        offers = self.offers.filter(is_published=True, starts_on__lte=today, ends_on__gte=today)
        return (
            max(offers, key=lambda offer: offer.saving(self.price), default=None)
            if self.price is not None
            else None
        )

    @property
    def effective_price(self):
        offer = self.current_offer
        return self.price - offer.saving(self.price) if offer else self.price

    @property
    def price_display(self):
        if self.price is None:
            return "Request pricing"
        amount = f"{self.effective_price:,.2f}".removesuffix(".00")
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

    booking_intro = models.TextField(
        default=(
            "Tell us the shape of your day. "
            "We will confirm timing, catering, and pricing in your proposal."
        )
    )
    require_event_times = models.BooleanField(default=False)
    walkthrough_intro = models.TextField(
        default=(
            "Come and see the space. Choose a published appointment, "
            "and the team will confirm your visit."
        )
    )
    catering_intro = models.TextField(
        default=(
            "Plan the table around your guests. Ask the team about the current menu, "
            "dietary needs, and catering arrangements."
        )
    )
    automated_email_enabled = models.BooleanField(default=False)
    automated_sms_enabled = models.BooleanField(default=False)
    reminder_days = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(14)]
    )
    feedback_delay_days = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(30)]
    )
    review_url = models.URLField(
        blank=True,
        help_text=(
            "Optional public review destination, shared after every event regardless of rating."
        ),
    )
    loyalty_enabled = models.BooleanField(default=False)
    loyalty_start_date = models.DateField(default=timezone.localdate)
    loyalty_points_per_event = models.PositiveSmallIntegerField(default=100)
    loyalty_description = models.TextField(
        default=(
            "Earn points for completed, confirmed events. "
            "Redeem points for rewards published by the venue."
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


class EventTypeOption(models.Model):
    code = models.SlugField(max_length=40, unique=True)
    label = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "pk"]

    def __str__(self):
        return self.label


class BookingQuestion(models.Model):
    class Kind(models.TextChoices):
        TEXT = "text", "Short answer"
        LONG = "long", "Long answer"
        SELECT = "select", "Choose an option"
        CHECK = "check", "Checkbox"

    label = models.CharField(max_length=180)
    help_text = models.CharField(max_length=300, blank=True)
    kind = models.CharField(max_length=10, choices=Kind, default=Kind.TEXT)
    options = models.TextField(blank=True, help_text="One choice per line, for a select question.")
    event_types = models.ManyToManyField(
        EventTypeOption, blank=True, help_text="Empty means all event types."
    )
    is_required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "pk"]

    def __str__(self):
        return self.label

    def clean(self):
        if self.kind == self.Kind.SELECT and not self.options.strip():
            raise ValidationError({"options": "Add at least one choice."})


class PackageOffer(models.Model):
    package = models.ForeignKey(EventPackage, on_delete=models.CASCADE, related_name="offers")
    title = models.CharField(max_length=120)
    percent_off = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    amount_off = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )
    starts_on = models.DateField(default=timezone.localdate)
    ends_on = models.DateField()
    terms = models.TextField(max_length=1000)
    is_published = models.BooleanField(default=False)

    def __str__(self):
        return self.title

    def clean(self):
        if bool(self.percent_off) == bool(self.amount_off):
            raise ValidationError("Set either a percentage or a fixed discount, not both.")
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValidationError({"ends_on": "End date must be on or after the start date."})

    def saving(self, price):
        if price is None:
            return Decimal("0")
        saving = price * self.percent_off / 100 if self.percent_off else self.amount_off
        return min(price, saving).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class CateringItem(models.Model):
    title = models.CharField(max_length=120)
    category = models.CharField(max_length=80, default="Menu")
    description = models.TextField(max_length=1000)
    dietary_notes = models.CharField(max_length=200, blank=True)
    price = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    price_note = models.CharField(
        max_length=120,
        blank=True,
        help_text="For example, per person. Do not include unconfirmed terms.",
    )
    is_published = models.BooleanField(default=False)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["category", "display_order", "pk"]

    def __str__(self):
        return self.title


class CateringOrder(models.Model):
    """
    A catering order placed from the menu. Prices are copied from the menu when the order is
    placed, so later menu changes never alter it. No payment is taken on the site: the venue
    confirms the order and arranges payment.
    """

    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(
        Booking,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="catering_orders",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    status = models.CharField(max_length=10, choices=Status, default=Status.RECEIVED)
    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=40)
    event_date = models.DateField("event date")
    guest_count = models.PositiveSmallIntegerField(
        "guests",
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(settings.BOOKING_MAX_GUESTS)],
    )
    notes = models.TextField("notes and dietary needs", max_length=2000, blank=True)
    total = models.DecimalField(
        "estimated total",
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Sum of the priced items when ordered. Items without a price are quoted.",
    )
    has_unpriced_items = models.BooleanField(default=False)
    created_at = models.DateTimeField("ordered", auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Catering for {self.name}, {self.event_date:%b %-d, %Y}"

    @property
    def total_display(self):
        amount = f"${self.total:,.2f}"
        return f"{amount} + quoted items" if self.has_unpriced_items else amount


class CateringOrderLine(models.Model):
    order = models.ForeignKey(CateringOrder, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(CateringItem, null=True, blank=True, on_delete=models.SET_NULL)
    title = models.CharField(max_length=120)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    price_note = models.CharField(max_length=120, blank=True)
    quantity = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(1000)]
    )

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return f"{self.quantity} × {self.title}"

    @property
    def line_total(self):
        return None if self.unit_price is None else self.unit_price * self.quantity


class WalkthroughSlot(models.Model):
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ["starts_at"]

    def __str__(self):
        return f"{timezone.localtime(self.starts_at):%b %d, %Y %I:%M %p}"

    def clean(self):
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "End must be after the start."})
        if (
            self.starts_at
            and self.ends_at
            and WalkthroughSlot.objects.filter(
                starts_at__lt=self.ends_at, ends_at__gt=self.starts_at, is_published=True
            )
            .exclude(pk=self.pk)
            .exists()
            and self.is_published
        ):
            raise ValidationError("That slot overlaps another published appointment slot.")


class WalkthroughAppointment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"
        DECLINED = "declined", "Declined"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    slot = models.ForeignKey(WalkthroughSlot, on_delete=models.PROTECT, related_name="appointments")
    status = models.CharField(max_length=10, choices=Status, default=Status.PENDING)
    notes = models.TextField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["slot__starts_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["slot"],
                condition=Q(status__in=["pending", "confirmed"]),
                name="one_active_walkthrough_per_slot",
            )
        ]

    def __str__(self):
        return f"{self.owner}: {self.slot}"


class RecentEvent(models.Model):
    PHOTO_CHOICES = [
        (name, name.replace("-", " ").title())
        for name in [
            "event-hall",
            "wedding-couple",
            "celebration",
            "meeting-room",
            "gallery-hall",
            "gallery-dance",
        ]
    ]
    title = models.CharField(max_length=160)
    event_date = models.DateField()
    category = models.CharField(max_length=80)
    summary = models.TextField(max_length=1500)
    photo = models.CharField(max_length=40, choices=PHOTO_CHOICES, default="event-hall")
    photo_caption = models.CharField(max_length=200, blank=True)
    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ["-event_date", "-pk"]

    def __str__(self):
        return self.title

    @property
    def image_path(self):
        return f"images/{self.photo}.jpg"

    def clean(self):
        if self.is_published and self.event_date and self.event_date > timezone.localdate():
            raise ValidationError({"event_date": "Recent events must have already taken place."})


class EventFeedback(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name="feedback")
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comments = models.TextField(max_length=3000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Feedback for {self.booking}"


class LoyaltyCredit(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    booking = models.OneToOneField(Booking, null=True, blank=True, on_delete=models.PROTECT)
    points = models.IntegerField()
    reason = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.owner}: {self.points} points"

    def clean(self):
        if self.booking_id and self.booking.owner_id != self.owner_id:
            raise ValidationError("The credit must belong to the event's owner.")


class LoyaltyReward(models.Model):
    title = models.CharField(max_length=120)
    description = models.TextField(max_length=1000)
    points_required = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    is_published = models.BooleanField(default=False)

    def __str__(self):
        return self.title


class RewardRedemption(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        APPROVED = "approved", "Approved"
        REDEEMED = "redeemed", "Redeemed"
        DECLINED = "declined", "Declined"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    reward = models.ForeignKey(LoyaltyReward, on_delete=models.PROTECT)
    title_snapshot = models.CharField(max_length=120)
    points = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=Status, default=Status.REQUESTED)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.owner}: {self.title_snapshot} ({self.status})"


class ScheduledNotification(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    booking = models.ForeignKey(Booking, null=True, blank=True, on_delete=models.CASCADE)
    appointment = models.ForeignKey(
        WalkthroughAppointment, null=True, blank=True, on_delete=models.CASCADE
    )
    kind = models.CharField(
        max_length=20,
        choices=[
            ("event", "Event reminder"),
            ("walkthrough", "Walkthrough reminder"),
            ("feedback", "Feedback invitation"),
        ],
    )
    channel = models.CharField(max_length=5, choices=[("email", "Email"), ("sms", "Text")])
    key = models.CharField(max_length=200, unique=True)
    reference_date = models.DateField()
    scheduled_for = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status, default=Status.QUEUED)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    provider_id = models.CharField(max_length=100, blank=True)
    last_error = models.CharField(max_length=200, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["scheduled_for"]

    def __str__(self):
        return f"{self.kind} / {self.channel}: {self.status}"
