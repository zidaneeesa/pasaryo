from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_POST

from .forms import UserAddressForm
from .models import UserAddress
from .views import read_json


def address_data(address):
    return {
        "id": address.pk,
        "label": address.label,
        "recipient_name": address.recipient_name,
        "recipient_phone": address.recipient_phone,
        "street_address": address.street_address,
        "subdistrict": address.subdistrict,
        "city": address.city,
        "province": address.province,
        "postal_code": address.postal_code,
        "is_main": address.is_main,
    }


def lock_address_owner(user):
    get_user_model().objects.select_for_update().get(pk=user.pk)


def address_conflict_response():
    return JsonResponse(
        {"message": "Perubahan alamat bertabrakan. Silakan ulangi permintaan."},
        status=409,
    )


@require_http_methods(["GET", "POST"])
def address_list_view(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"message": "Silakan login terlebih dahulu."}, status=401
        )

    if request.method == "GET":
        addresses = UserAddress.objects.filter(user=request.user).order_by(
            "-is_main", "pk"
        )
        return JsonResponse({
            "results": [address_data(address) for address in addresses]
        })

    data = read_json(request)
    if data is None:
        return JsonResponse(
            {"message": "Body harus berupa objek JSON."}, status=400
        )

    form = UserAddressForm(data)
    if not form.is_valid():
        return JsonResponse(
            {"errors": form.errors.get_json_data()}, status=400
        )

    try:
        with transaction.atomic():
            lock_address_owner(request.user)
            address = form.save(commit=False)
            address.user = request.user
            address.is_main = not UserAddress.objects.filter(
                user=request.user
            ).exists()
            address.save()
    except IntegrityError:
        return address_conflict_response()

    return JsonResponse({
        "message": "Alamat berhasil ditambahkan.",
        "address": address_data(address),
    }, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
def address_detail_view(request, address_id):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"message": "Silakan login terlebih dahulu."}, status=401
        )

    if request.method == "GET":
        address = UserAddress.objects.filter(
            pk=address_id, user=request.user
        ).first()
        if address is None:
            return JsonResponse(
                {"message": "Alamat tidak ditemukan."}, status=404
            )
        return JsonResponse({"address": address_data(address)})

    if request.method == "PATCH":
        data = read_json(request)
        if data is None:
            return JsonResponse(
                {"message": "Body harus berupa objek JSON."}, status=400
            )

    try:
        with transaction.atomic():
            lock_address_owner(request.user)
            address = UserAddress.objects.filter(
                pk=address_id, user=request.user
            ).first()
            if address is None:
                return JsonResponse(
                    {"message": "Alamat tidak ditemukan."}, status=404
                )

            if request.method == "DELETE":
                was_main = address.is_main
                address.delete()

                if was_main:
                    replacement = UserAddress.objects.filter(
                        user=request.user
                    ).order_by("pk").first()

                    if replacement is not None:
                        replacement.is_main = True
                        replacement.save(update_fields=["is_main"])

                return JsonResponse({
                    "message": "Alamat berhasil dihapus."
                })

            values = {
                name: getattr(address, name)
                for name in UserAddressForm.base_fields
            }
            values.update({
                name: data[name] for name in values if name in data
            })

            form = UserAddressForm(values, instance=address)
            if not form.is_valid():
                return JsonResponse(
                    {"errors": form.errors.get_json_data()}, status=400
                )

            address = form.save(commit=False)
            address.save(
                update_fields=list(UserAddressForm.base_fields)
            )
    except IntegrityError:
        return address_conflict_response()

    return JsonResponse({
        "message": "Alamat berhasil diperbarui.",
        "address": address_data(address),
    })


@require_POST
def address_main_view(request, address_id):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"message": "Silakan login terlebih dahulu."}, status=401
        )

    try:
        with transaction.atomic():
            lock_address_owner(request.user)
            address = UserAddress.objects.filter(
                pk=address_id, user=request.user
            ).first()
            if address is None:
                return JsonResponse(
                    {"message": "Alamat tidak ditemukan."}, status=404
                )

            UserAddress.objects.filter(
                user=request.user,
                is_main=True,
            ).exclude(pk=address.pk).update(is_main=False)

            address.is_main = True
            address.save(update_fields=["is_main"])
    except IntegrityError:
        return address_conflict_response()

    return JsonResponse({
        "message": "Alamat utama berhasil diubah.",
        "address": address_data(address),
    })