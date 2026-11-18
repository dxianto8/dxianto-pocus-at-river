from dataclasses import dataclass
from datetime import date

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Case, IntegerField, Value, When
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from . import services
from .calendar import add_months, month_dates
from .models import (
    HALVES,
    Activity,
    Booking,
    BookingQuestion,
    CateringItem,
    CateringOrder,
    CateringOrderLine,
    ChecklistItem,
    CustomerProfile,
    Document,
    EventFeedback,
    EventPackage,
    EventTypeOption,
    LoyaltyCredit,
    LoyaltyReward,
    Message,
    PackageOffer,
    RecentEvent,
    RewardRedemption,
    ScheduledNotification,
    ScheduleItem,
    VenueSettings,
    WalkthroughAppointment,
    WalkthroughSlot,
)
from .views import safe_parse_date

STATUS_COLOURS = {
    Booking.Status.PENDING: "#b26a00",
    Booking.Status.CONFIRMED: "#263822",
    Booking.Status.DECLINED: "#7a7a7a",
    Booking.Status.CANCELLED: "#7a7a7a",
    Booking.Status.BLOCKED: "#363636",
}


@dataclass(frozen=True)
class AdminDay:
    date: date
    in_month: bool
    is_past: bool
    is_today: bool
    bookings: list[Booking]
    open_sessions: list[str]  # what can still be blocked or added on this date


class MessageInline(admin.TabularInline):
    """The conversation with the customer. Add a row to reply; sent messages can't be edited."""

    model = Message
    extra = 1
    fields = ["sender", "body", "created_at"]
    readonly_fields = ["sender", "created_at"]
    can_delete = False
    verbose_name = "message"
    verbose_name_plural = "Messages with the customer (add a row to reply)"

    @admin.display(description="From")
    def sender(self, message: Message):
        if message.pk is None:
            return "You (venue)"
        return "Venue" if message.from_staff else "Customer"

    def has_change_permission(self, request, obj=None):
        return False


class ChecklistInline(admin.TabularInline):
    model = ChecklistItem
    extra = 0
    fields = ["title", "due_date", "done_at", "from_staff"]
    verbose_name_plural = "Checklist (the customer sees and ticks these)"


class ScheduleInline(admin.TabularInline):
    model = ScheduleItem
    extra = 0
    verbose_name_plural = "Day schedule (written by the customer)"


class DocumentInlineForm(forms.ModelForm):
    upload = forms.FileField(
        required=False, help_text="PDF, Word, Excel, text, JPG or PNG, up to 4 MB."
    )

    class Meta:
        model = Document
        fields = ["title"]

    def clean(self):
        data = super().clean()
        upload = data.get("upload")
        if upload:
            try:
                Document.check_upload(upload)
            except forms.ValidationError as error:
                self.add_error("upload", error)
        elif self.instance._state.adding:
            self.add_error("upload", "Choose a file to share.")
        return data

    def save(self, commit=True):
        if self.cleaned_data.get("upload"):
            self.instance.attach(self.cleaned_data["upload"])
        return super().save(commit=commit)


class DocumentInline(admin.TabularInline):
    model = Document
    form = DocumentInlineForm
    extra = 0
    fields = ["title", "upload", "file", "shared_by", "created_at"]
    readonly_fields = ["file", "shared_by", "created_at"]
    verbose_name_plural = "Documents (proposals, contracts, floor plans)"

    def get_queryset(self, request):
        return super().get_queryset(request).defer("data")

    @admin.display(description="Stored file")
    def file(self, document: Document):
        if document._state.adding:
            return "-"
        url = reverse("admin:bookings_booking_document", args=[document.pk])
        return format_html('<a href="{}">{}</a>', url, document.filename)

    @admin.display(description="From")
    def shared_by(self, document: Document):
        if document._state.adding:
            return "You (venue)"
        return "Venue" if document.from_staff else "Customer"


class ActivityInline(admin.TabularInline):
    model = Activity
    extra = 0
    fields = ["text", "created_at"]
    readonly_fields = ["text", "created_at"]
    can_delete = False
    verbose_name_plural = "History (also shown to the customer)"

    def has_add_permission(self, request, obj=None):
        return False


class EventTypeAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = list(EventTypeOption.objects.filter(is_active=True).values_list("code", "label"))
        current = self.instance.event_type
        if current and current not in dict(choices):
            choices.append((current, self.instance.get_event_type_display()))
        self.fields["event_type"] = forms.ChoiceField(choices=choices or Booking.EventType.choices)


class CateringOrderInline(admin.TabularInline):
    model = CateringOrder
    fields = ["created_at", "status", "total", "has_unpriced_items"]
    readonly_fields = ["created_at", "total", "has_unpriced_items"]
    extra = 0
    show_change_link = True
    can_delete = False
    verbose_name_plural = "catering orders"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    form = EventTypeAdminForm
    inlines = [
        MessageInline,
        DocumentInline,
        ChecklistInline,
        ScheduleInline,
        CateringOrderInline,
        ActivityInline,
    ]
    autocomplete_fields = ["owner", "package"]
    list_display = [
        "event_date",
        "session",
        "status_badge",
        "name",
        "event_type",
        "guest_count",
        "email",
        "owner",
        "unread",
        "created_at",
    ]
    list_display_links = ["event_date", "name"]
    list_filter = ["status", "session", "event_type"]
    date_hierarchy = "event_date"
    search_fields = ["name", "email", "phone", "message", "admin_note", "owner__username"]
    actions = ["confirm", "decline", "cancel"]
    fieldsets = [
        (None, {"fields": ["event_date", "session", "status"]}),
        ("Contact", {"fields": ["owner", "name", "email", "phone"]}),
        (
            "Event",
            {
                "fields": [
                    "event_type",
                    "package",
                    "package_snapshot",
                    "price_snapshot",
                    "guest_count",
                    "start_time",
                    "end_time",
                    "catering_interest",
                    "dietary_notes",
                    "questionnaire_answers",
                    "message",
                ]
            },
        ),
        ("Internal", {"fields": ["admin_note", "created_at", "updated_at"]}),
    ]
    readonly_fields = ["created_at", "updated_at", "package_snapshot", "price_snapshot"]
    change_list_template = "admin/bookings/booking/change_list.html"

    def get_ordering(self, request):
        # Pending requests first (they need a decision), then by event date.
        pending_first = Case(
            When(status=Booking.Status.PENDING, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
        return [pending_first.asc(), "event_date"]

    @admin.display(description="Status", ordering="status")
    def status_badge(self, booking: Booking):
        return format_html(
            '<span style="display:inline-block;padding:2px 8px;border-radius:9px;color:#fff;'
            'background:{};font-size:11px;font-weight:600">{}</span>',
            STATUS_COLOURS[booking.status],
            booking.get_status_display(),
        )

    @admin.display(description="New from customer")
    def unread(self, booking: Booking):
        count = booking.messages.filter(from_staff=False, read_at=None).count()
        return f"{count} message{'s' if count != 1 else ''}" if count else ""

    # Keeping the customer in step ------------------------------------------------------------

    def get_inlines(self, request, obj):
        # A venue block has no customer, so there is nothing to talk about or plan.
        if obj is None or obj.status == Booking.Status.BLOCKED:
            return []
        return self.inlines

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if request.method == "GET":  # opening the booking marks the customer's messages read
            Message.objects.filter(booking_id=object_id, from_staff=False, read_at=None).update(
                read_at=timezone.now()
            )
        return super().change_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change and "status" in form.changed_data:
            services.status_changed(obj, by_staff=True, request=request)
        if change and ("event_date" in form.changed_data or "session" in form.changed_data):
            services.log(obj, f"The venue moved the event to {obj.when}.")

    def save_formset(self, request, form, formset, change):
        booking = form.instance
        for instance in formset.save(commit=False):
            adding = instance._state.adding
            if isinstance(instance, Message) and adding:
                instance.from_staff, instance.author = True, request.user
                instance.save()
                services.notify_customer(
                    booking, "New message from the venue", [instance.body], request
                )
                continue
            if isinstance(instance, Document) and adding:
                instance.from_staff, instance.uploaded_by = True, request.user
                instance.save()
                services.log(booking, f"The venue shared “{instance.title}”."[:200])
                services.notify_customer(
                    booking,
                    "A new document for your event",
                    [f"The venue team shared “{instance.title}” with you."],
                    request,
                )
                continue
            if isinstance(instance, ChecklistItem) and adding:
                instance.from_staff = True
            instance.save()
        for removed in formset.deleted_objects:
            removed.delete()
        formset.save_m2m()

    def document_view(self, request: HttpRequest, pk) -> HttpResponse:
        if not self.has_view_permission(request):
            raise PermissionDenied
        document = get_object_or_404(Document, pk=pk)
        response = HttpResponse(bytes(document.data), content_type=document.content_type)
        name = "".join(c for c in document.filename if c.isalnum() or c in "._- ") or "document"
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        response["X-Content-Type-Options"] = "nosniff"
        return response

    # Bulk actions ---------------------------------------------------------------------------

    def _move(self, request, queryset, from_statuses, to_status, verb):
        moving = list(queryset.filter(status__in=from_statuses))
        count = queryset.filter(status__in=from_statuses).update(
            status=to_status, updated_at=timezone.now()
        )
        for booking in moving:
            booking.status = to_status
            services.status_changed(booking, by_staff=True, request=request)
        skipped = queryset.count() - count
        self.message_user(request, f"{verb} {count} booking(s).", messages.SUCCESS)
        if skipped:
            self.message_user(
                request,
                f"Skipped {skipped} that weren't in a state that allows this.",
                messages.WARNING,
            )

    @admin.action(description="Confirm selected pending requests", permissions=["change"])
    def confirm(self, request, queryset):
        self._move(
            request, queryset, [Booking.Status.PENDING], Booking.Status.CONFIRMED, "Confirmed"
        )

    @admin.action(
        description="Decline selected pending requests (frees the date)", permissions=["change"]
    )
    def decline(self, request, queryset):
        self._move(request, queryset, [Booking.Status.PENDING], Booking.Status.DECLINED, "Declined")

    @admin.action(description="Cancel selected bookings (frees the date)", permissions=["change"])
    def cancel(self, request, queryset):
        self._move(
            request,
            queryset,
            [Booking.Status.PENDING, Booking.Status.CONFIRMED],
            Booking.Status.CANCELLED,
            "Cancelled",
        )

    # Calendar page --------------------------------------------------------------------------

    def get_urls(self):
        custom = [
            path(
                "document/<uuid:pk>/",
                self.admin_site.admin_view(self.document_view),
                name="bookings_booking_document",
            ),
            path(
                "calendar/",
                self.admin_site.admin_view(self.calendar_view),
                name="bookings_booking_calendar",
            ),
            path(
                "calendar/block/",
                self.admin_site.admin_view(require_POST(self.block_view)),
                name="bookings_booking_block",
            ),
            path(
                "calendar/<uuid:pk>/unblock/",
                self.admin_site.admin_view(require_POST(self.unblock_view)),
                name="bookings_booking_unblock",
            ),
        ]
        return custom + super().get_urls()

    def calendar_view(self, request: HttpRequest) -> HttpResponse:
        if not self.has_view_permission(request):
            raise PermissionDenied
        today = timezone.localdate()
        first = self._parse_month(request.GET.get("month"), today)
        weeks = month_dates(first)
        bookings: dict[date, list[Booking]] = {}
        for b in (
            Booking.objects.active()
            .filter(event_date__range=(weeks[0][0], weeks[-1][-1]))
            .order_by("event_date", "session")
        ):
            bookings.setdefault(b.event_date, []).append(b)

        def open_sessions(day):
            held = {h for b in bookings.get(day, []) for h in HALVES[b.session]}
            return [s for s in Booking.Session.values if not held & set(HALVES[s])]

        context = {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "title": f"Calendar: {first:%B %Y}",
            "month": first,
            "previous": f"{add_months(first, -1):%Y-%m}",
            "next": f"{add_months(first, 1):%Y-%m}",
            "this_month": f"{today:%Y-%m}",
            "weekdays": ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
            "weeks": [
                [
                    AdminDay(
                        d,
                        d.month == first.month,
                        d < today,
                        d == today,
                        bookings.get(d, []),
                        open_sessions(d),
                    )
                    for d in week
                ]
                for week in weeks
            ],
            "can_add": self.has_add_permission(request),
            "can_delete": self.has_delete_permission(request),
            "add_url": reverse("admin:bookings_booking_add"),
        }
        return TemplateResponse(request, "admin/bookings/booking/calendar.html", context)

    def block_view(self, request: HttpRequest) -> HttpResponse:
        if not self.has_add_permission(request):
            raise PermissionDenied
        day = safe_parse_date(request.POST.get("date"))
        if day is None or day < timezone.localdate():
            self.message_user(request, "Choose a date that hasn't passed.", messages.ERROR)
            return self._back_to_calendar(day)
        session = request.POST.get("session", Booking.Session.FULL)
        if session not in Booking.Session.values:
            session = Booking.Session.FULL
        label = f"{day:%a %d %b %Y} ({Booking.Session(session).label})"
        try:
            with transaction.atomic():
                Booking.objects.create(
                    event_date=day, session=session, status=Booking.Status.BLOCKED
                )
        except IntegrityError:
            self.message_user(request, f"{label} already has a booking.", messages.ERROR)
        else:
            self.message_user(request, f"Blocked {label}.", messages.SUCCESS)
        return self._back_to_calendar(day)

    def unblock_view(self, request: HttpRequest, pk) -> HttpResponse:
        if not self.has_delete_permission(request):
            raise PermissionDenied
        booking = get_object_or_404(Booking, pk=pk, status=Booking.Status.BLOCKED)
        day = booking.event_date
        booking.delete()
        self.message_user(request, f"Unblocked {day:%a %d %b %Y}.", messages.SUCCESS)
        return self._back_to_calendar(day)

    @staticmethod
    def _parse_month(value: str | None, today: date) -> date:
        try:
            year, month = (int(part) for part in (value or "").split("-"))
            return date(year, month, 1)
        except ValueError:
            return today.replace(day=1)

    @staticmethod
    def _back_to_calendar(day: date | None) -> HttpResponse:
        url = reverse("admin:bookings_booking_calendar")
        if day:
            url += "?" + urlencode({"month": f"{day:%Y-%m}"})
        return HttpResponseRedirect(url)


@admin.register(EventPackage)
class EventPackageAdmin(admin.ModelAdmin):
    form = EventTypeAdminForm
    list_display = ["title", "event_type", "price", "price_unit", "is_published", "display_order"]
    list_filter = ["event_type", "is_published"]
    search_fields = ["title", "description"]
    prepopulated_fields = {"slug": ["title"]}
    fieldsets = [
        ("Package", {"fields": ["title", "slug", "event_type", "description"]}),
        ("Pricing (USD)", {"fields": ["price", "price_unit", "starting_at", "price_note"]}),
        ("What's included", {"fields": ["inclusions"]}),
        ("Publishing", {"fields": ["is_published", "display_order"]}),
    ]


@admin.register(VenueSettings)
class VenueSettingsAdmin(admin.ModelAdmin):
    fieldsets = [
        ("Venue & contact", {"fields": ["name", "contact_email", "phone", "address"]}),
        ("Homepage", {"fields": ["hero_heading"]}),
        ("Packages page", {"fields": ["pricing_intro", "pricing_note"]}),
    ] + [
        (
            "Booking questionnaire",
            {
                "fields": ["booking_intro", "require_event_times"],
                "description": (
                    "Manage Event type options and Booking questions "
                    "for the form's choices and custom fields."
                ),
            },
        ),
        ("Visits and catering", {"fields": ["walkthrough_intro", "catering_intro"]}),
        (
            "Email, texting, and feedback",
            {
                "fields": [
                    "messaging_status",
                    "automated_email_enabled",
                    "automated_sms_enabled",
                    "reminder_days",
                    "feedback_delay_days",
                    "review_url",
                ],
                "description": (
                    "Provider credentials belong in deployment environment variables. "
                    "Reminders are opt-in and run from the daily scheduler."
                ),
            },
        ),
        (
            "Loyalty",
            {
                "fields": [
                    "loyalty_enabled",
                    "loyalty_start_date",
                    "loyalty_points_per_event",
                    "loyalty_description",
                ]
            },
        ),
    ]

    readonly_fields = ["messaging_status"]

    def messaging_status(self, obj):
        return "SendGrid: {} · Twilio: {} · Scheduler token: {}".format(
            "configured" if settings.SENDGRID_API_KEY else "not configured (SMTP fallback)",
            "configured"
            if all(
                [
                    settings.TWILIO_ACCOUNT_SID,
                    settings.TWILIO_AUTH_TOKEN,
                    settings.TWILIO_FROM_NUMBER,
                ]
            )
            else "not configured",
            "configured" if settings.CRON_SECRET else "not configured",
        )

    def has_add_permission(self, request):
        return not VenueSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


# Venue services share the same staff-only administration and validation as bookings.


@admin.register(EventTypeOption)
class EventTypeOptionAdmin(admin.ModelAdmin):
    list_display = ["label", "code", "is_active", "display_order"]
    prepopulated_fields = {"code": ["label"]}
    list_filter = ["is_active"]
    search_fields = ["label"]

    def get_readonly_fields(self, request, obj=None):
        return ["code"] if obj else []

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BookingQuestion)
class BookingQuestionAdmin(admin.ModelAdmin):
    list_display = ["label", "kind", "is_required", "is_active", "display_order"]
    list_filter = ["is_active", "kind", "event_types"]
    filter_horizontal = ["event_types"]


@admin.register(PackageOffer)
class PackageOfferAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "package",
        "percent_off",
        "amount_off",
        "starts_on",
        "ends_on",
        "is_published",
    ]
    list_filter = ["is_published", "package"]


@admin.register(CateringItem)
class CateringItemAdmin(admin.ModelAdmin):
    list_display = ["title", "category", "price", "is_published", "display_order"]
    list_filter = ["category", "is_published"]
    search_fields = ["title", "description"]


class CateringOrderLineInline(admin.TabularInline):
    model = CateringOrderLine
    fields = ["title", "quantity", "unit_price", "price_note"]
    readonly_fields = ["title", "unit_price", "price_note"]
    extra = 0


@admin.register(CateringOrder)
class CateringOrderAdmin(admin.ModelAdmin):
    list_display = ["created_at", "name", "event_date", "status", "total", "booking", "owner"]
    list_filter = ["status"]
    search_fields = ["name", "email", "phone", "notes"]
    date_hierarchy = "event_date"
    autocomplete_fields = ["booking", "owner"]
    inlines = [CateringOrderLineInline]
    readonly_fields = ["created_at", "total", "has_unpriced_items"]
    fieldsets = [
        (None, {"fields": ["status", "booking", "owner", "created_at"]}),
        ("Contact", {"fields": ["name", "email", "phone"]}),
        ("Event", {"fields": ["event_date", "guest_count", "notes"]}),
        (
            "Price",
            {
                "fields": ["total", "has_unpriced_items"],
                "description": "Prices were copied from the menu when the order was placed. "
                "No payment is taken on the site.",
            },
        ),
    ]


@admin.register(WalkthroughSlot)
class WalkthroughSlotAdmin(admin.ModelAdmin):
    list_display = ["starts_at", "ends_at", "is_published"]
    list_filter = ["is_published"]
    date_hierarchy = "starts_at"

    def get_readonly_fields(self, request, obj=None):
        # Do not move an appointment out from under a customer's confirmed visit.
        if obj and obj.appointments.filter(status__in=["pending", "confirmed"]).exists():
            return ["starts_at", "ends_at"]
        return []


@admin.register(WalkthroughAppointment)
class WalkthroughAppointmentAdmin(admin.ModelAdmin):
    list_display = ["owner", "slot", "status", "created_at"]
    list_filter = ["status"]
    readonly_fields = ["owner", "slot", "notes", "created_at"]

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if "status" in form.changed_data:
            services.notify_appointment(
                obj, f"Walkthrough {obj.get_status_display().lower()}", request
            )


@admin.register(RecentEvent)
class RecentEventAdmin(admin.ModelAdmin):
    list_display = ["title", "event_date", "category", "is_published"]
    list_filter = ["is_published", "category"]
    search_fields = ["title", "summary"]


@admin.register(EventFeedback)
class EventFeedbackAdmin(admin.ModelAdmin):
    list_display = ["booking", "rating", "created_at"]
    list_filter = ["rating"]
    readonly_fields = ["booking", "rating", "comments", "created_at"]

    def has_add_permission(self, request):
        return False


@admin.register(LoyaltyReward)
class LoyaltyRewardAdmin(admin.ModelAdmin):
    list_display = ["title", "points_required", "is_published"]
    list_filter = ["is_published"]


@admin.register(LoyaltyCredit)
class LoyaltyCreditAdmin(admin.ModelAdmin):
    list_display = ["owner", "points", "reason", "created_at"]
    autocomplete_fields = ["owner"]

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RewardRedemption)
class RewardRedemptionAdmin(admin.ModelAdmin):
    list_display = ["owner", "title_snapshot", "points", "status", "created_at"]
    list_filter = ["status"]
    readonly_fields = ["owner", "reward", "title_snapshot", "points", "created_at"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "email_updates", "sms_reminders", "feedback_updates"]
    readonly_fields = ["user", "phone", "email_updates", "sms_reminders", "feedback_updates"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ScheduledNotification)
class ScheduledNotificationAdmin(admin.ModelAdmin):
    list_display = ["owner", "kind", "channel", "scheduled_for", "status", "attempts"]
    list_filter = ["status", "channel", "kind"]
    readonly_fields = [field.name for field in ScheduledNotification._meta.fields]
    actions = ["retry_failed"]

    def has_add_permission(self, request):
        return False

    @admin.action(description="Retry selected failed notifications")
    def retry_failed(self, request, queryset):
        count = queryset.filter(status="failed").update(
            status="queued", attempts=0, last_attempt_at=None, last_error=""
        )
        self.message_user(request, f"Queued {count} failed notification(s) for retry.")

    def has_delete_permission(self, request, obj=None):
        return False
