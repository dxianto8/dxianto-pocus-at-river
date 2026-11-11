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
