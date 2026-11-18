from datetime import UTC, datetime, timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Max, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from bookings import services
from bookings.forms import (
    BookingEditForm,
    ChecklistItemForm,
    DocumentForm,
    MessageForm,
    ScheduleItemForm,
)
from bookings.models import Booking, ChecklistItem, Document, EventPackage, Message

from .forms import ProfileForm, RegistrationForm


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
    destination = safe_next(request) or reverse("bookings:book")
    if request.user.is_authenticated:
        return redirect(destination or "accounts:dashboard")
    # Someone who just made a request in this browser has already given their name and email.
    from_request = services.guest_details(request)
    form = RegistrationForm(
        request.POST if request.method == "POST" else None,
        initial={k: v for k, v in from_request.items() if k in ("first_name", "email")},
    )
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = form.save()
        except IntegrityError:
            form.add_error("username", "That username is unavailable. Please choose another.")
        else:
            if from_request.get("phone"):
                profile = services.profile_for(user)
                profile.phone = from_request["phone"]
                profile.save(update_fields=["phone"])
            login(request, user)  # also moves this browser's requests into the new account
            return redirect(destination or "accounts:dashboard")
    return render(
        request,
        "accounts/signup.html",
        {"form": form, "next": destination, "from_request": bool(from_request)},
    )


def attention_for(user, today):
    """Things waiting on the customer across all their events, most pressing first."""
    items = []
    events = Booking.objects.filter(owner=user)
    unread = (
        events.filter(messages__from_staff=True, messages__read_at=None)
        .annotate(n=Count("messages"))
        .order_by("event_date")
    )
    for booking in unread:
        items.append(
            {
                "kind": "message",
                "text": f"{booking.n} new message{'s' if booking.n > 1 else ''} from the venue",
                "booking": booking,
                "url": reverse("accounts:booking_messages", args=[booking.pk]),
            }
        )
    for doc in (
        Document.objects.filter(booking__owner=user, from_staff=True, seen_at=None)
        .select_related("booking")
        .defer("data")
    ):
        items.append(
            {
                "kind": "document",
                "text": f"New document: {doc.title}",
                "booking": doc.booking,
                "url": reverse("accounts:booking_documents", args=[doc.booking_id]),
            }
        )
    due = ChecklistItem.objects.filter(
        booking__owner=user,
        booking__status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED],
        booking__event_date__gte=today,
        done_at=None,
        due_date__lte=today + timedelta(days=14),
    ).select_related("booking")
    for item in due[:6]:
        items.append(
            {
                "kind": "overdue" if item.is_overdue else "task",
                "text": item.title,
                "due": item.due_date,
                "booking": item.booking,
                "url": reverse("accounts:booking_checklist", args=[item.booking_id]),
            }
        )
    return items


@never_cache
@login_required
@require_GET
def dashboard(request):
    today = timezone.localdate()
    bookings = (
        Booking.objects.filter(owner=request.user)
        .select_related("package")
        .annotate(
            unread=Count("messages", filter=Q(messages__from_staff=True, messages__read_at=None))
        )
        .order_by("-created_at")
    )
    counts = bookings.aggregate(
        total=Count("pk", distinct=True),
        pending=Count("pk", filter=Q(status=Booking.Status.PENDING), distinct=True),
        confirmed=Count("pk", filter=Q(status=Booking.Status.CONFIRMED), distinct=True),
    )
    next_event = (
        bookings.filter(
            event_date__gte=today,
            status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED],
        )
        .order_by("event_date")
        .first()
    )
    selected_status = request.GET.get("status", "")
    if selected_status == "completed":
        bookings = bookings.filter(status="confirmed", event_date__lt=today)
    elif selected_status == "upcoming":
        bookings = bookings.filter(status__in=["pending", "confirmed"], event_date__gte=today)
    elif selected_status in Booking.Status.values and selected_status != Booking.Status.BLOCKED:
        bookings = bookings.filter(status=selected_status)
    else:
        selected_status = ""
    next_tasks = []
    if next_event:
        next_tasks = list(next_event.checklist.filter(done_at=None)[:3])
    return render(
        request,
        "accounts/dashboard.html",
        {
            "bookings": bookings,
            "counts": counts,
            "next_event": next_event,
            "next_tasks": next_tasks,
            "selected_status": selected_status,
            "attention": attention_for(request.user, today),
            "filters": [
                ("", "All"),
                ("upcoming", "Upcoming"),
                ("completed", "Completed"),
                ("pending", "Pending"),
                ("confirmed", "Confirmed"),
                ("cancelled", "Cancelled"),
                ("declined", "Declined"),
            ],
        },
    )


def owned_event(view):
    """Look up the signed-in customer's own event, or 404. Never cached."""

    @never_cache
    @login_required
    @wraps(view)
    def wrapper(request, pk, *args, **kwargs):
        booking = get_object_or_404(
            Booking.objects.select_related("package"), pk=pk, owner=request.user
        )
        return view(request, booking, *args, **kwargs)

    return wrapper


def event_page(request, booking, tab, template, **context):
    return render(
        request,
        template,
        {
            "booking": booking,
            "tab": tab,
            "tabs": [
                ("overview", "Overview", reverse("accounts:booking_detail", args=[booking.pk]), 0),
                (
                    "messages",
                    "Messages",
                    reverse("accounts:booking_messages", args=[booking.pk]),
                    booking.messages.filter(from_staff=True, read_at=None).count(),
                ),
                (
                    "checklist",
                    "Checklist",
                    reverse("accounts:booking_checklist", args=[booking.pk]),
                    booking.checklist.filter(done_at=None).count(),
                ),
                (
                    "schedule",
                    "Day schedule",
                    reverse("accounts:booking_schedule", args=[booking.pk]),
                    0,
                ),
                (
                    "documents",
                    "Documents",
                    reverse("accounts:booking_documents", args=[booking.pk]),
                    booking.documents.filter(from_staff=True, seen_at=None).count(),
                ),
            ],
            **context,
        },
    )


def back_to(name, booking):
    return redirect(reverse(name, args=[booking.pk]))


@require_GET
@owned_event
def booking_detail(request, booking):
    checklist = booking.checklist.all()
    return event_page(
        request,
        booking,
        "overview",
        "accounts/booking_detail.html",
        activity=booking.activity.all()[:12],
        next_tasks=[item for item in checklist if not item.is_done][:4],
        tasks_done=sum(item.is_done for item in checklist),
        tasks_total=len(checklist),
        last_message=booking.messages.last(),
    )


@require_http_methods(["GET", "POST"])
@owned_event
def booking_edit(request, booking):
    if not booking.can_edit:
        messages.info(
            request, "This event can no longer be changed here. Message the venue team instead."
        )
        return back_to("accounts:booking_messages", booking)
    old_date, old_when = booking.event_date, booking.when
    form = BookingEditForm(request.POST or None, instance=booking)
    if request.method == "POST" and form.is_valid():
        changed = form.changed_data
        try:
            with transaction.atomic():
                booking = form.save()
        except IntegrityError:
            form.add_error("session", "That date or time of day was just taken. Choose another.")
        else:
            if changed:
                if "event_date" in changed:
                    services.shift_checklist(booking, old_date)
                if "event_date" in changed or "session" in changed:
                    services.log(
                        booking, f"You moved the request from {old_when} to {booking.when}."
                    )
                others = [
                    form.fields[name].label.replace(" (optional)", "").lower()
                    for name in changed
                    if name not in ("event_date", "session")
                ]
                if others:
                    services.log(booking, f"You updated {', '.join(others)}.")
                services.notify_venue(
                    booking,
                    f"Request updated: {booking.name}, {booking.event_date:%B %-d, %Y}",
                    ["The customer changed: " + ", ".join(changed) + "."],
                    request,
                )
                messages.success(request, "Changes saved.")
            return back_to("accounts:booking_detail", booking)
    return event_page(request, booking, "overview", "accounts/booking_edit.html", form=form)


@require_http_methods(["GET", "POST"])
@owned_event
def booking_cancel(request, booking):
    if not booking.can_cancel:
        return back_to("accounts:booking_detail", booking)
    if request.method == "POST":
        booking.status = Booking.Status.CANCELLED
        booking.save(update_fields=["status", "updated_at"])
        services.status_changed(booking, by_staff=False, request=request)
        messages.success(request, "Event cancelled. The date is no longer held for you.")
        return back_to("accounts:booking_detail", booking)
    return event_page(request, booking, "overview", "accounts/booking_cancel.html")


@require_GET
@owned_event
def booking_ics(request, booking):
    venue = services._venue()
    end = booking.event_date + timedelta(days=1)

    def esc(text):
        return (
            str(text)
            .replace("\\", "\\\\")
            .replace(",", "\\,")
            .replace(";", "\\;")
            .replace("\n", "\\n")
        )

    if booking.start_time and booking.end_time:
        start_at = timezone.make_aware(datetime.combine(booking.event_date, booking.start_time))
        end_at = timezone.make_aware(datetime.combine(booking.event_date, booking.end_time))
        dates = [
            f"DTSTART:{start_at.astimezone(UTC):%Y%m%dT%H%M%SZ}",
            f"DTEND:{end_at.astimezone(UTC):%Y%m%dT%H%M%SZ}",
        ]
    else:
        dates = [
            f"DTSTART;VALUE=DATE:{booking.event_date:%Y%m%d}",
            f"DTEND;VALUE=DATE:{end:%Y%m%d}",
        ]
    status = "CONFIRMED" if booking.status == Booking.Status.CONFIRMED else "TENTATIVE"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Pocus at River//Event workspace//EN",
        "BEGIN:VEVENT",
        f"UID:{booking.pk}@pocusatriver",
        f"DTSTAMP:{timezone.now():%Y%m%dT%H%M%SZ}",
        *dates,
        f"SUMMARY:{esc(booking.get_event_type_display())} at {esc(venue.name)}",
        f"LOCATION:{esc(venue.address)}",
        f"STATUS:{status}",
        f"DESCRIPTION:{esc(booking.get_status_display())}. {esc(booking.guest_count)} guests.",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    response = HttpResponse(
        "\r\n".join(lines) + "\r\n", content_type="text/calendar; charset=utf-8"
    )
    response["Content-Disposition"] = (
        f'attachment; filename="pocus-{booking.event_date:%Y-%m-%d}.ics"'
    )
    return response


@require_http_methods(["GET", "POST"])
@owned_event
def booking_messages(request, booking):
    form = MessageForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        Message.objects.create(booking=booking, author=request.user, body=form.cleaned_data["body"])
        services.notify_venue(
            booking,
            f"New message: {booking.name}, {booking.event_date:%B %-d, %Y}",
            [form.cleaned_data["body"]],
            request,
        )
        messages.success(request, "Message sent.")
        return redirect(reverse("accounts:booking_messages", args=[booking.pk]) + "#latest")
    thread = list(booking.messages.select_related("author"))
    booking.messages.filter(from_staff=True, read_at=None).update(read_at=timezone.now())
    return event_page(
        request, booking, "messages", "accounts/booking_messages.html", form=form, thread=thread
    )


@require_http_methods(["GET", "POST"])
@owned_event
def booking_checklist(request, booking):
    form = ChecklistItemForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ChecklistItem.objects.create(booking=booking, **form.cleaned_data)
        return back_to("accounts:booking_checklist", booking)
    items = list(booking.checklist.all())
    return event_page(
        request,
        booking,
        "checklist",
        "accounts/booking_checklist.html",
        form=form,
        open_items=[i for i in items if not i.is_done],
        done_items=[i for i in items if i.is_done],
        total=len(items),
    )


@require_POST
@owned_event
def checklist_item(request, booking, item_id):
    item = get_object_or_404(ChecklistItem, pk=item_id, booking=booking)
    if request.POST.get("action") == "delete":
        if not item.from_staff:
            item.delete()
    else:
        item.done_at = None if item.is_done else timezone.now()
        item.save(update_fields=["done_at"])
    return back_to("accounts:booking_checklist", booking)


@require_http_methods(["GET", "POST"])
@owned_event
def booking_schedule(request, booking):
    form = ScheduleItemForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        booking.schedule.create(**form.cleaned_data)
        return back_to("accounts:booking_schedule", booking)
    return event_page(
        request,
        booking,
        "schedule",
        "accounts/booking_schedule.html",
        form=form,
        items=booking.schedule.all(),
    )


@require_POST
@owned_event
def schedule_item(request, booking, item_id):
    get_object_or_404(booking.schedule, pk=item_id).delete()
    return back_to("accounts:booking_schedule", booking)


@require_http_methods(["GET", "POST"])
@owned_event
def booking_documents(request, booking):
    form = DocumentForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["file"]
        document = Document(
            booking=booking,
            title=form.cleaned_data["title"] or upload.name[:160],
            uploaded_by=request.user,
        )
        document.attach(upload)
        document.save()
        services.log(booking, f"You added the document “{document.title}”."[:200])
        services.notify_venue(
            booking,
            f"New document: {booking.name}, {booking.event_date:%B %-d, %Y}",
            [f"The customer uploaded “{document.title}”."],
            request,
        )
        messages.success(request, "Document added.")
        return back_to("accounts:booking_documents", booking)
    documents = list(booking.documents.defer("data"))
    booking.documents.filter(from_staff=True, seen_at=None).update(seen_at=timezone.now())
    return event_page(
        request,
        booking,
        "documents",
        "accounts/booking_documents.html",
        form=form,
        documents=documents,
    )


@require_http_methods(["GET", "POST"])
@owned_event
def document(request, booking, document_id):
    doc = get_object_or_404(Document, pk=document_id, booking=booking)
    if request.method == "POST":
        if not doc.from_staff:
            doc.delete()
            messages.success(request, "Document removed.")
        return back_to("accounts:booking_documents", booking)
    response = HttpResponse(bytes(doc.data), content_type=doc.content_type)
    safe_name = "".join(c for c in doc.filename if c.isalnum() or c in "._- ") or "document"
    response["Content-Disposition"] = f'attachment; filename="{safe_name}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


@never_cache
@login_required
@require_GET
def inbox(request):
    threads = (
        Booking.objects.filter(owner=request.user)
        .annotate(
            last=Max("messages__created_at"),
            unread=Count("messages", filter=Q(messages__from_staff=True, messages__read_at=None)),
        )
        .order_by(F("last").desc(nulls_last=True), "event_date")
    )
    rows = []
    for booking in threads:
        rows.append({"booking": booking, "latest": booking.messages.last()})
    return render(request, "accounts/inbox.html", {"rows": rows})


@never_cache
@login_required
@require_GET
def packages(request):
    return render(
        request,
        "packages.html",
        {
            "packages": EventPackage.objects.published(),
            "layout_template": "accounts/workspace_base.html",
        },
    )


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def settings(request):
    form = ProfileForm(
        request.POST or None, instance=request.user, profile=services.profile_for(request.user)
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        update_session_auth_hash(request, request.user)
        messages.success(request, "Profile saved.")
        return redirect("accounts:settings")
    return render(request, "accounts/settings.html", {"form": form})
