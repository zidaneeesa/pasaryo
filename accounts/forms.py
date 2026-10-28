from django import forms
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import BaseUserCreationForm

User = get_user_model()


class RegisterForm(BaseUserCreationForm):
    class Meta:
        model = User
        fields = ["full_name", "email"]

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Email sudah terdaftar.")

        return email


class LoginForm(forms.Form):
    email = forms.EmailField(max_length=254)
    password = forms.CharField(strip=False)

    def clean_email(self):
        return self.cleaned_data["email"].lower()

class ProfileForm(forms.ModelForm):
    date_of_birth = forms.DateField(
        required=False,
        input_formats=["%Y-%m-%d"],
    )

    class Meta:
        model = User
        fields = ["full_name", "phone", "date_of_birth"]

    def clean_date_of_birth(self):
        date_of_birth = self.cleaned_data.get("date_of_birth")

        if date_of_birth and date_of_birth > timezone.localdate():
            raise forms.ValidationError(
                "Tanggal lahir tidak boleh di masa depan."
            )

        return date_of_birth