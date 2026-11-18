"""
Ordering catering from the published menu. Open to everyone, like booking a date: visitors
without an account can order for a request they made in this browser, or for a date they
have not booked yet. Prices are copied onto the order. No payment is taken on the site.
"""

from decimal import Decimal
from uuid import UUID

from django import forms
from django.conf import settings
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from . import services
from .models import Booking, CateringItem, CateringOrder, CateringOrderLine
from .views import layout_for

ORDER_SESSION_KEY = "guest_catering_orders"
MAX_QUANTITY = 1000


class CateringOrderForm(forms.Form):
    event = forms.ModelChoiceField(
        queryset=Booking.objects.none(),
        required=False,
        label="Which event is this for?",
        empty_label="A date I have not booked yet",
    )
    event_date = forms.DateField(
        label="Event date",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    guest_count = forms.IntegerField(
        label="Number of guests",
        min_value=1,
        max_value=settings.BOOKING_MAX_GUESTS,
        required=False,
    )
    name = forms.CharField(label="Your name", max_length=120)
    email = forms.EmailField(label="Email")
    phone = forms.CharField(label="Phone", max_length=40)
    notes = forms.CharField(
        label="Notes and dietary needs (optional)",
        max_length=2000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    # Honeypot: hidden from people, but bots that fill in every field will fill this too.
    website = forms.CharField(required=False, label="Leave this field empty")

    def __init__(self, *args, items, booking=None, events=None, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
        self.items = items
        self.booking = booking
        today = timezone.localdate()
        if booking is not None or not events:
            del self.fields["event"]
        else:
            self.fields["event"].queryset = events
        if booking is not None:
            del self.fields["event_date"]
        else:
            self.fields["event_date"].widget.attrs["min"] = today.isoformat()
            self.fields["event_date"].help_text = "Leave empty if you chose a booked event above."
            if "event" not in self.fields:
                self.fields["event_date"].required = True
                self.fields["event_date"].help_text = ""
        self.fields["guest_count"].widget.attrs.update(min=1, max=settings.BOOKING_MAX_GUESTS)
        for name, autocomplete in [("name", "name"), ("email", "email"), ("phone", "tel")]:
            self.fields[name].widget.attrs["autocomplete"] = autocomplete
        self.fields["website"].widget.attrs.update(tabindex="-1", autocomplete="off")
        for item in items:
            self.fields[self.quantity_name(item)] = forms.IntegerField(
                label=f"How many: {item.title}",
                min_value=0,
                max_value=MAX_QUANTITY,
                required=False,
                widget=forms.NumberInput(
                    attrs={
                        "min": 0,
                        "max": MAX_QUANTITY,
                        "step": 1,
                        "inputmode": "numeric",
                        "class": "qty__input",
                        "data-price": "" if item.price is None else f"{item.price}",
                        "placeholder": "0",
                    }
                ),
            )

    @staticmethod
    def quantity_name(item) -> str:
        return f"qty_{item.pk}"

    @property
    def is_spam(self) -> bool:
        return bool(self.cleaned_data.get("website"))

    @property
    def contact_fields(self):
        return [self[name] for name in ("name", "email", "phone") if name in self.fields]

    @property
    def event_fields(self):
        return [
            self[name] for name in ("event", "event_date", "guest_count") if name in self.fields
        ]

    def quantity_field(self, item):
        return self[self.quantity_name(item)]

    def chosen(self):
        """[(item, quantity)] for every item ordered, in menu order."""
        return [
            (item, self.cleaned_data.get(self.quantity_name(item)) or 0)
            for item in self.items
            if self.cleaned_data.get(self.quantity_name(item))
        ]

    def clean_event_date(self):
        day = self.cleaned_data.get("event_date")
        if day and day < timezone.localdate():
            raise forms.ValidationError("That date has already passed.")
        return day

    def clean(self):
        data = super().clean()
        if self.booking is None and not data.get("event") and not data.get("event_date"):
            self.add_error("event_date", "Choose your event or enter its date.")
        if self.items and not self.chosen() and "website" not in self.errors:
            raise forms.ValidationError("Choose at least one item from the menu.")
        if not self.items and not data.get("notes"):
            self.add_error("notes", "Tell us what you would like to order.")
        return data


def booking_for(request):
    """The request this order is for (?booking=). Only its owner or guest session may use it."""
    value = request.GET.get("booking")
    if not value:
        return None
    try:
        booking = Booking.objects.get(pk=UUID(value))
    except (ValueError, Booking.DoesNotExist):
        raise Http404 from None
    if not services.can_view_booking(request, booking):
        raise Http404
    return booking


@never_cache
@require_http_methods(["GET", "POST"])
def catering_order(request):
    booking = booking_for(request)
    user = request.user if request.user.is_authenticated else None
    items = list(CateringItem.objects.filter(is_published=True))
    events = None
    if user and booking is None:
        events = Booking.objects.active().filter(owner=user, event_date__gte=timezone.localdate())
    initial = {}
    if booking is not None:
        initial = {
            "name": booking.name,
            "email": booking.email,
            "phone": booking.phone,
            "guest_count": booking.guest_count,
        }
    elif user:
        initial = {
            "name": user.get_full_name() or user.username,
            "email": user.email,
            "phone": services.profile_for(user).phone,
        }
    form = CateringOrderForm(
        request.POST if request.method == "POST" else None,
        items=items,
        booking=booking,
        events=events,
        initial=initial,
    )
    if request.method == "POST" and form.is_valid():
        if form.is_spam:  # pretend it worked, save nothing
            return redirect("catering")
        order = place_order(request, form, booking or form.cleaned_data.get("event"), user)
        return redirect("catering_order_detail", pk=order.pk)
    return render(
        request,
        "catering_order.html",
        {
            "form": form,
            "menu": [{"item": item, "field": form.quantity_field(item)} for item in items],
            "detail_fields": [
                *form.event_fields,
                *form.contact_fields,
                form["notes"],
                form["website"],
            ],
            "booking": booking,
            "layout_template": layout_for(request),
        },
    )


def place_order(request, form, booking, user) -> CateringOrder:
    data = form.cleaned_data
    chosen = form.chosen()
    total = sum(
        (item.price * quantity for item, quantity in chosen if item.price is not None),
        Decimal("0"),
    )
    with transaction.atomic():
        order = CateringOrder.objects.create(
            booking=booking,
            owner=user or (booking.owner if booking else None),
            name=data["name"],
            email=data["email"],
            phone=data["phone"],
            event_date=booking.event_date if booking else data["event_date"],
            guest_count=data.get("guest_count") or (booking.guest_count if booking else None),
            notes=data.get("notes", ""),
            total=total,
            has_unpriced_items=any(item.price is None for item, _ in chosen),
        )
        CateringOrderLine.objects.bulk_create(
            CateringOrderLine(
                order=order,
                item=item,
                title=item.title,
                unit_price=item.price,
                price_note=item.price_note,
                quantity=quantity,
            )
            for item, quantity in chosen
        )
        if booking is not None and not booking.catering_interest:
            booking.catering_interest = True
            booking.save(update_fields=["catering_interest", "updated_at"])
    if booking is not None:
        services.log(booking, f"You ordered catering ({order.total_display}).")
    if user is None:
        ids = request.session.get(ORDER_SESSION_KEY, [])
        request.session[ORDER_SESSION_KEY] = [*ids, str(order.pk)][-10:]
    services.notify_catering_order(order, request)
    return order


def can_view_order(request, order) -> bool:
    if request.user.is_authenticated and order.owner_id == request.user.pk:
        return True
    return str(order.pk) in request.session.get(ORDER_SESSION_KEY, [])


@never_cache
@require_GET
def catering_order_detail(request, pk):
    order = get_object_or_404(
        CateringOrder.objects.select_related("booking").prefetch_related("lines"), pk=pk
    )
    if not can_view_order(request, order):
        raise Http404
    return render(
        request,
        "catering_order_detail.html",
        {"order": order, "layout_template": layout_for(request)},
    )
