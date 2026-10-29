from django import forms
from django.utils import timezone
from django.contrib.auth import get_user_model
from .models import UserAddress
from django.contrib.auth.forms import BaseUserCreationForm

User = get_user_model()


# Form untuk menangani validasi registrasi pengguna baru.
# Menggunakan BaseUserCreationForm bawaan Django agar password otomatis di-hash dan divalidasi keamanannya.
class RegisterForm(BaseUserCreationForm):
    class Meta:
        model = User
        fields = ["full_name", "email"]

    # Validasi custom email: normalisasi ke huruf kecil (lowercase) dan hapus spasi,
    # serta memastikan email belum terdaftar di database secara case-insensitive.
    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Email sudah terdaftar.")

        return email


# Form autentikasi login pengguna.
# Menggunakan form biasa (bukan ModelForm) karena hanya untuk memvalidasi kredensial (email & password).
class LoginForm(forms.Form):
    email = forms.EmailField(max_length=254)
    password = forms.CharField(strip=False)

    # Memastikan email input selalu dalam format lowercase sebelum dicocokkan ke database.
    def clean_email(self):
        return self.cleaned_data["email"].lower()


# Form pembaruan data profil pengguna (nama lengkap, nomor telepon, tanggal lahir).
# Menggunakan ModelForm agar perubahan langsung dapat disimpan ke instance User.
class ProfileForm(forms.ModelForm):
    date_of_birth = forms.DateField(
        required=False,
        input_formats=["%Y-%m-%d"],
    )

    class Meta:
        model = User
        fields = ["full_name", "phone", "date_of_birth"]

    # Validasi logika bisnis tanggal lahir:
    # Mencegah pengguna memasukkan tanggal lahir di masa depan (tidak valid secara logika).
    def clean_date_of_birth(self):
        date_of_birth = self.cleaned_data.get("date_of_birth")

        if date_of_birth and date_of_birth > timezone.localdate():
            raise forms.ValidationError(
                "Tanggal lahir tidak boleh di masa depan."
            )

        return date_of_birth


# Form pengelolaan alamat pengiriman pengguna (UserAddress).
# Dilengkapi validasi Regex untuk format nomor HP dan kode pos Indonesia.
class UserAddressForm(forms.ModelForm):
    recipient_phone = forms.RegexField(
        regex=r"^\+?[0-9]{8,15}$",
        max_length=20,
        error_messages={
            "invalid": "Nomor telepon harus 8-15 digit, boleh diawali +."
        },
    )
    postal_code = forms.RegexField(
        regex=r"^[0-9]{5}$",
        max_length=5,
        error_messages={
            "invalid": "Kode pos harus terdiri dari 5 digit."
        },
    )

    class Meta:
        model = UserAddress
        fields = [
            "label",
            "recipient_name",
            "recipient_phone",
            "street_address",
            "subdistrict",
            "city",
            "province",
            "postal_code",
        ]

    # Validasi menyeluruh (cross-field validation):
    # Memastikan semua field yang dikirim berformat teks (string) guna mencegah injection tipe data aneh.
    def clean(self):
        data = super().clean()
        for name in self.fields:
            if name in self.data and not isinstance(self.data[name], str):
                self.add_error(name, "Nilai harus berupa teks.")
        return data