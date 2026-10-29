import json

from django.contrib.auth import authenticate, login, logout
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .forms import LoginForm, RegisterForm

from django.contrib.auth import (
    authenticate,
    login,
    logout,
    update_session_auth_hash,
)
from django.contrib.auth.forms import PasswordChangeForm

from .forms import LoginForm, ProfileForm, RegisterForm


# Membaca request body sebagai JSON dict, return None jika invalid
def read_json(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    return data if isinstance(data, dict) else None


# Mengubah objek User menjadi dict untuk response JSON
def user_data(user):
    return {
        "id": user.pk,
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "date_of_birth": user.date_of_birth,
        "role": user.role,
    }


# Mengembalikan CSRF token untuk keperluan client SPA
@never_cache
@require_GET
def csrf_view(request):
    return JsonResponse({"csrf_token": get_token(request)})


# Registrasi user baru, validasi via RegisterForm lalu simpan ke database
@require_POST
def register_view(request):
    data = read_json(request)
    if data is None:
        return JsonResponse(
            {"message": "Body harus berupa objek JSON."},
            status=400,
        )

    form = RegisterForm(data)
    if not form.is_valid():
        return JsonResponse(
            {"errors": form.errors.get_json_data()},
            status=400,
        )

    try:
        with transaction.atomic():
            user = form.save()
    except IntegrityError:
        return JsonResponse(
            {"message": "Email sudah terdaftar."},
            status=409,
        )

    return JsonResponse(
        {
            "message": "Registrasi berhasil.",
            "user": user_data(user),
        },
        status=201,
    )


# Login user dengan email + password, buat session dan return CSRF token baru
@require_POST
def login_view(request):
    data = read_json(request)
    if data is None:
        return JsonResponse(
            {"message": "Body harus berupa objek JSON."},
            status=400,
        )

    form = LoginForm(data)
    if not form.is_valid():
        return JsonResponse(
            {"errors": form.errors.get_json_data()},
            status=400,
        )

    user = authenticate(
        request,
        email=form.cleaned_data["email"],
        password=form.cleaned_data["password"],
    )

    if user is None:
        return JsonResponse(
            {"message": "Email atau password salah."},
            status=401,
        )

    login(request, user)

    return JsonResponse({
        "message": "Login berhasil.",
        "user": user_data(user),
        "csrf_token": get_token(request),
    })


# Mengembalikan data profil user yang sedang login
@never_cache
@require_GET
def me_view(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"message": "Silakan login terlebih dahulu."},
            status=401,
        )

    return JsonResponse({"user": user_data(request.user)})


# Logout user, menghapus session
@require_POST
def logout_view(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"message": "Silakan login terlebih dahulu."},
            status=401,
        )

    logout(request)
    return JsonResponse({"message": "Logout berhasil."})


# Update profil user (partial update, field yang tidak dikirim tetap pakai nilai lama)
@never_cache
@require_POST
def profile_update_view(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"message": "Silakan login terlebih dahulu."},
            status=401,
        )

    data = read_json(request)
    if data is None:
        return JsonResponse(
            {"message": "Body harus berupa objek JSON."},
            status=400,
        )

    profile_data = {
        field: data.get(field, getattr(request.user, field))
        for field in ProfileForm.Meta.fields
    }

    form = ProfileForm(profile_data, instance=request.user)

    if not form.is_valid():
        return JsonResponse(
            {"errors": form.errors.get_json_data()},
            status=400,
        )

    user = form.save(commit=False)
    user.save(update_fields=ProfileForm.Meta.fields)

    return JsonResponse({
        "message": "Profil berhasil diperbarui.",
        "user": user_data(user),
    })


# Ganti password user, pakai PasswordChangeForm bawaan Django
@never_cache
@require_POST
def password_change_view(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"message": "Silakan login terlebih dahulu."},
            status=401,
        )

    data = read_json(request)
    if data is None:
        return JsonResponse(
            {"message": "Body harus berupa objek JSON."},
            status=400,
        )

    form = PasswordChangeForm(user=request.user, data=data)

    if not form.is_valid():
        return JsonResponse(
            {"errors": form.errors.get_json_data()},
            status=400,
        )

    user = form.save(commit=False)
    user.save(update_fields=["password"])

    update_session_auth_hash(request, user)

    return JsonResponse({
        "message": "Password berhasil diubah.",
        "csrf_token": get_token(request),
    })