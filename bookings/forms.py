from django import forms
from django.db.models import Q
from django.utils import timezone
from django.utils.html import escape

from .calendar import bookable_range
from .models import Booking, Document, EventPackage


class QuestionnaireMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import BookingQuestion, EventTypeOption, VenueSettings

        self.venue_config = VenueSettings.objects.filter(pk=1).first() or VenueSettings()
        choices = list(EventTypeOption.objects.filter(is_active=True).values_list("code", "label"))
        current = self.instance.event_type
        if current and current not in dict(choices):
            choices.append((current, self.instance.get_event_type_display()))
        self.event_choices = choices or list(Booking.EventType.choices)
        self.fields["event_type"] = forms.ChoiceField(
            label="Event type", choices=self.event_choices
        )
        for field in ("start_time", "end_time"):
            self.fields[field].required = self.venue_config.require_event_times
            self.fields[field].widget = forms.TimeInput(attrs={"type": "time"}, format="%H:%M")
            self.fields[field].label = field.replace("_", " ").capitalize()
            self.fields[field].help_text = "Chicago time. Confirmed in your proposal."
        self.questions = list(
            BookingQuestion.objects.filter(is_active=True).prefetch_related("event_types")
        )
        previous = {
            a.get("question_id"): a.get("answer") for a in self.instance.questionnaire_answers
        }
        for question in self.questions:
            types = [option.code for option in question.event_types.all()]
            options = [
                (line.strip(), line.strip())
                for line in question.options.splitlines()
                if line.strip()
            ]
            attrs = {
                "data-event-types": ",".join(types),
                "data-question-required": str(question.is_required).lower(),
            }
            if question.kind == "check":
                field = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs=attrs))
            elif question.kind == "select":
                field = forms.ChoiceField(
                    required=False,
                    choices=[("", "Choose one"), *options],
                    widget=forms.Select(attrs=attrs),
                )
            else:
                widget = (
                    forms.Textarea(attrs={**attrs, "rows": 3})
                    if question.kind == "long"
                    else forms.TextInput(attrs=attrs)
                )
                field = forms.CharField(required=False, max_length=2000, widget=widget)
            field.label = question.label
            field.help_text = escape(question.help_text)
            name = f"question_{question.pk}"
            self.fields[name] = field
            self.initial.setdefault(name, previous.get(question.pk))

    def clean(self):
        data = super().clean()
        start, end = data.get("start_time"), data.get("end_time")
        if bool(start) != bool(end):
            self.add_error(
                "end_time" if start else "start_time", "Add both a start and an end time."
            )
        event_type = data.get("event_type")
        self.answer_snapshot = []
        for question in self.questions:
            types = [option.code for option in question.event_types.all()]
            if types and event_type not in types:
                continue
            name = f"question_{question.pk}"
            value = data.get(name)
            if question.is_required and not value and name not in self.errors:
                self.add_error(name, "Please answer this question.")
            self.answer_snapshot.append(
                {"question_id": question.pk, "question": question.label, "answer": value}
            )
        return data

    def save(self, commit=True):
        # Retain answers to questions that staff have since archived.
        active_ids = {question.pk for question in self.questions}
        archived = [
            a for a in self.instance.questionnaire_answers if a.get("question_id") not in active_ids
        ]
        self.instance.questionnaire_answers = archived + self.answer_snapshot
        return super().save(commit=commit)


class BookingRequestForm(QuestionnaireMixin, forms.ModelForm):
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
            "start_time",
            "end_time",
            "catering_interest",
            "dietary_notes",
            "message",
        ]
        labels = {
            "name": "Your name",
            "guest_count": "Number of guests",
            "phone": "Phone (optional)",
            "message": "Tell us about your event (optional)",
            "catering_interest": "I would like to discuss catering",
            "dietary_notes": "Dietary or catering notes (optional)",
            "package": "Preferred package (optional)",
        }
        widgets = {
            "event_date": forms.HiddenInput,
            "message": forms.Textarea(attrs={"rows": 5}),
            "dietary_notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["package"].queryset = EventPackage.objects.published()
        self.fields["package"].empty_label = "Help me choose"
        if user is not None:
            self.fields["email"].disabled = True
            self.initial["email"] = user.email
            self.initial.setdefault("name", user.get_full_name() or user.username)
        for name in ("name", "email", "event_type", "guest_count"):
            self.fields[name].required = True
        self.fields["event_type"].choices = [("", "Choose one")] + self.event_choices
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


class BookingEditForm(QuestionnaireMixin, forms.ModelForm):
    """What a customer may change on their own pending request, including the date."""

    class Meta:
        model = Booking
        fields = [
            "event_date",
            "name",
            "phone",
            "event_type",
            "package",
            "guest_count",
            "start_time",
            "end_time",
            "catering_interest",
            "dietary_notes",
            "message",
        ]
        labels = {
            "event_date": "Event date",
            "name": "Contact name",
            "guest_count": "Number of guests",
            "phone": "Phone (optional)",
            "message": "About your event (optional)",
            "catering_interest": "I would like to discuss catering",
            "dietary_notes": "Dietary or catering notes (optional)",
            "package": "Preferred package (optional)",
        }
        widgets = {
            "event_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "message": forms.Textarea(attrs={"rows": 5}),
            "dietary_notes": forms.Textarea(attrs={"rows": 3}),
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
        self.fields["package"].queryset = EventPackage.objects.filter(
            Q(pk=self.instance.package_id) | Q(pk__in=EventPackage.objects.published().values("pk"))
        )
        self.fields["package"].empty_label = "Help me choose"
        for name in ("name", "event_type", "guest_count"):
            self.fields[name].required = True
        self.fields["event_type"].choices = self.event_choices
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
