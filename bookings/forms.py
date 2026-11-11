from django import forms
from django.utils import timezone

from .calendar import bookable_range
from .models import Booking


class BookingRequestForm(forms.ModelForm):
    """The public request form. Every request starts as pending; visitors cannot set a status."""

    # Honeypot: hidden from people, but bots that fill in every field will fill this too.
    website = forms.CharField(required=False, label="Leave this field empty")

    class Meta:
        model = Booking
        fields = ["event_date", "name", "email", "phone", "event_type", "guest_count", "message"]
        labels = {
            "name": "Your name",
            "guest_count": "Number of guests",
            "phone": "Phone (optional)",
            "message": "Tell us about your event (optional)",
        }
        widgets = {
            "event_date": forms.HiddenInput,
            "message": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
        for name in ("name", "email", "event_type", "guest_count"):
            self.fields[name].required = True
        self.fields["event_type"].choices = [("", "Choose one")] + list(Booking.EventType.choices)
        self.fields["name"].widget.attrs["autocomplete"] = "name"
        self.fields["email"].widget.attrs["autocomplete"] = "email"
        self.fields["phone"].widget.attrs["autocomplete"] = "tel"
        self.fields["guest_count"].widget.attrs.update(min=1, max=200)
        self.fields["website"].widget.attrs.update(tabindex="-1", autocomplete="off")

    @property
    def is_spam(self) -> bool:
        return bool(self.cleaned_data.get("website"))

    def clean_event_date(self):
        day = self.cleaned_data["event_date"]
        first, last = bookable_range(timezone.localdate())
        if day < first:
            raise forms.ValidationError("That date has already passed.")
        if day > last:
            raise forms.ValidationError("We take requests up to 24 months ahead.")
        if Booking.objects.active().filter(event_date=day).exists():
            raise forms.ValidationError("Sorry, that date is no longer available.")
        return day

    def save(self, commit=True):
        self.instance.status = Booking.Status.PENDING
        return super().save(commit=commit)
