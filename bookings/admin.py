from dataclasses import dataclass
from datetime import date

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

from .calendar import add_months, month_dates
from .models import Booking
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
    booking: Booking | None


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = [
        "event_date",
        "status_badge",
        "name",
        "event_type",
        "guest_count",
        "email",
        "created_at",
    ]
    list_display_links = ["event_date", "name"]
    list_filter = ["status", "event_type"]
    date_hierarchy = "event_date"
    search_fields = ["name", "email", "phone", "message", "admin_note"]
    actions = ["confirm", "decline", "cancel"]
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = [
        (None, {"fields": ["event_date", "status"]}),
        ("Contact", {"fields": ["name", "email", "phone"]}),
        ("Event", {"fields": ["event_type", "guest_count", "message"]}),
        ("Internal", {"fields": ["admin_note", "created_at", "updated_at"]}),
    ]
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

    # Bulk actions ---------------------------------------------------------------------------

    def _move(self, request, queryset, from_statuses, to_status, verb):
        count = queryset.filter(status__in=from_statuses).update(
            status=to_status, updated_at=timezone.now()
        )
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
        bookings = {
            b.event_date: b
            for b in Booking.objects.active().filter(event_date__range=(weeks[0][0], weeks[-1][-1]))
        }
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
                    AdminDay(d, d.month == first.month, d < today, d == today, bookings.get(d))
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
        try:
            with transaction.atomic():
                Booking.objects.create(event_date=day, status=Booking.Status.BLOCKED)
        except IntegrityError:
            self.message_user(request, f"{day:%a %d %b %Y} already has a booking.", messages.ERROR)
        else:
            self.message_user(request, f"Blocked {day:%a %d %b %Y}.", messages.SUCCESS)
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
