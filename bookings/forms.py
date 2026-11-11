from django import forms
from django.utils import timezone

from .calendar import bookable_range
from .models import Booking, EventPackage


class BookingRequestForm(forms.ModelForm):
    """The public request form. Every request starts as pending; visitors cannot set a status."""

    # Honeypot: hidden from people, but bots that fill in every field will fill this too.
    website = forms.CharField(required=False, label="Leave this field empty")

    class Meta:
        model = Booking
        fields = [
            "event_date",
            "name",
            "email",
            "phone",
            "event_type",
            "package",
            "guest_count",
            "message",
        ]
        labels = {
            "name": "Your name",
            "guest_count": "Number of guests",
            "phone": "Phone (optional)",
            "message": "Tell us about your event (optional)",
            "package": "Preferred package (optional)",
        }
        widgets = {
            "event_date": forms.HiddenInput,
            "message": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, user=None, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["package"].queryset = EventPackage.objects.filter(is_published=True)
        self.fields["package"].empty_label = "Help me choose"
        if user is not None:
            self.fields["email"].disabled = True
            self.initial["email"] = user.email
            self.initial.setdefault("name", user.get_full_name() or user.username)
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
        if self.user is not None:
            self.instance.owner = self.user
            self.instance.email = self.user.email
        package = self.cleaned_data.get("package")
        if package:
            self.instance.package_snapshot = package.title
            self.instance.price_snapshot = package.price_display
        return super().save(commit=commit)

    def clean(self):
        data = super().clean()
        package = data.get("package")
        if package and package.event_type != data.get("event_type"):
            self.add_error(
                "package", "Choose a package that matches your event type, or Help me choose."
            )
        return data
