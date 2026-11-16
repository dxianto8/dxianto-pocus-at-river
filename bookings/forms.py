from django import forms
from django.utils import timezone

from .calendar import bookable_range
from .models import Booking, Document, EventPackage


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


class BookingEditForm(forms.ModelForm):
    """What a customer may change on their own pending request, including the date."""

    class Meta:
        model = Booking
        fields = ["event_date", "name", "phone", "event_type", "package", "guest_count", "message"]
        labels = {
            "event_date": "Event date",
            "name": "Contact name",
            "guest_count": "Number of guests",
            "phone": "Phone (optional)",
            "message": "About your event (optional)",
            "package": "Preferred package (optional)",
        }
        widgets = {
            "event_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "message": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
        self.old_date = self.instance.event_date
        first, last = bookable_range(timezone.localdate())
        self.fields["event_date"].widget.attrs.update(min=first.isoformat(), max=last.isoformat())
        self.fields[
            "event_date"
        ].help_text = "Changing the date moves your hold to the new date if it is free."
        self.fields["package"].queryset = EventPackage.objects.filter(is_published=True)
        self.fields["package"].empty_label = "Help me choose"
        for name in ("name", "event_type", "guest_count"):
            self.fields[name].required = True
        self.fields["event_type"].choices = list(Booking.EventType.choices)
        self.fields["guest_count"].widget.attrs.update(min=1, max=200)

    def clean_event_date(self):
        day = self.cleaned_data["event_date"]
        if day == self.old_date:
            return day
        first, last = bookable_range(timezone.localdate())
        if day < first:
            raise forms.ValidationError("That date has already passed.")
        if day > last:
            raise forms.ValidationError("We take requests up to 24 months ahead.")
        if Booking.objects.active().filter(event_date=day).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("That date is taken. Choose another one.")
        return day

    def clean(self):
        data = super().clean()
        package = data.get("package")
        if package and package.event_type != data.get("event_type"):
            self.add_error(
                "package", "Choose a package that matches your event type, or Help me choose."
            )
        return data

    def save(self, commit=True):
        if "package" in self.changed_data:
            package = self.cleaned_data.get("package")
            self.instance.package_snapshot = package.title if package else ""
            self.instance.price_snapshot = package.price_display if package else ""
        return super().save(commit=commit)


class MessageForm(forms.Form):
    body = forms.CharField(
        label="Your message",
        max_length=4000,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Write to the venue team"}),
    )


class ChecklistItemForm(forms.Form):
    title = forms.CharField(label="Add a task", max_length=160)
    due_date = forms.DateField(
        label="Due (optional)", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )


class ScheduleItemForm(forms.Form):
    time = forms.TimeField(label="Time", widget=forms.TimeInput(attrs={"type": "time"}))
    title = forms.CharField(label="What happens", max_length=160)
    note = forms.CharField(label="Note (optional)", max_length=250, required=False)


class DocumentForm(forms.Form):
    title = forms.CharField(
        label="Name (optional)",
        max_length=160,
        required=False,
        help_text="Shown in the list. Leave empty to use the file name.",
    )
    file = forms.FileField(
        label="File", help_text="PDF, Word, Excel, text, JPG or PNG, up to 4 MB."
    )

    def clean_file(self):
        upload = self.cleaned_data["file"]
        Document.check_upload(upload)
        return upload
