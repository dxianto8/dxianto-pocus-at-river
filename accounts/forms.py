import re

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(label="Your name", max_length=150)
    website = forms.CharField(required=False, label="Leave this field empty")

    class Meta:
        model = User
        fields = ["first_name", "email", "username", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ""
        for field, autocomplete in [
            ("first_name", "name"),
            ("email", "email"),
            ("username", "username"),
        ]:
            self.fields[field].widget.attrs["autocomplete"] = autocomplete
        self.fields["website"].widget.attrs.update(tabindex="-1", autocomplete="off")

    def clean_website(self):
        if self.cleaned_data["website"]:
            raise forms.ValidationError("Please leave this field empty.")
        return ""


class ProfileForm(forms.ModelForm):
    """Name, email and phone. Changing the email needs the current password."""

    phone = forms.CharField(required=False, max_length=40, label="Phone (optional)")
    email_updates = forms.BooleanField(
        required=False,
        label="Email me about my events",
        help_text="Status changes, new messages and new documents.",
    )
    sms_reminders = forms.BooleanField(
        required=False,
        label="Text me event and walkthrough reminders",
        help_text=(
            "Optional. Message and data rates may apply. Reply STOP to opt out. "
            "Use an international phone number, such as +13125550123."
        ),
    )
    feedback_updates = forms.BooleanField(
        required=False,
        label="Invite me to share feedback after an event",
        help_text="Email invitations, and text invitations if you also enable texting.",
    )
    current_password = forms.CharField(
        required=False,
        label="Current password",
        help_text="Only needed when you change your email.",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        labels = {"first_name": "First name", "last_name": "Last name (optional)"}

    def __init__(self, *args, profile, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
        self.profile = profile
        self.fields["first_name"].required = True
        self.fields["email"].required = True
        self.initial.update(
            phone=profile.phone,
            email_updates=profile.email_updates,
            sms_reminders=profile.sms_reminders,
            feedback_updates=profile.feedback_updates,
        )
        for field, autocomplete in [
            ("first_name", "given-name"),
            ("last_name", "family-name"),
            ("email", "email"),
            ("phone", "tel"),
        ]:
            self.fields[field].widget.attrs["autocomplete"] = autocomplete

    def clean(self):
        data = super().clean()
        if data.get("sms_reminders") and not re.fullmatch(
            r"\+[1-9]\d{6,14}", data.get("phone", "")
        ):
            self.add_error(
                "phone", "Use an international number, for example +13125550123, to enable texting."
            )
        changed_email = (
            data.get("email")
            and data["email"] != self.instance.__class__.objects.get(pk=self.instance.pk).email
        )
        if changed_email and not self.instance.check_password(data.get("current_password", "")):
            self.add_error("current_password", "Enter your current password to change your email.")
        return data

    def save(self, commit=True):
        user = super().save(commit=commit)
        self.profile.phone = self.cleaned_data["phone"]
        self.profile.email_updates = self.cleaned_data["email_updates"]
        self.profile.sms_reminders = self.cleaned_data["sms_reminders"]
        self.profile.feedback_updates = self.cleaned_data["feedback_updates"]
        self.profile.save()
        return user
