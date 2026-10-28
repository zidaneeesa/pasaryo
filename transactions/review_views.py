from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from accounts.views import read_json

from .models import Order, OrderItem, Review
from .review_forms import ReviewForm


def review_data(review):
    item = review.order_item
    variant = item.product_variant

    return {
        "id": review.pk,
        "order_item_id": item.pk,
        "product_id": variant.product_id if variant else None,
        "product_name": item.product_name_snapshot,
        "variant_name": item.variant_name_snapshot,
        "rating": review.rating,
        "comment": review.comment,
        "created_at": review.created_at.isoformat(),
    }


@require_POST
def review_create_view(request):
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

    if set(data) - {"order_item_id", "rating", "comment"}:
        return JsonResponse(
            {"message": "Ada field yang tidak diizinkan."},
            status=400,
        )

    item_id = data.get("order_item_id")

    if type(item_id) is not int or item_id < 1:
        return JsonResponse(
            {
                "message": (
                    "order_item_id harus berupa "
                    "bilangan bulat positif."
                )
            },
            status=400,
        )

    form = ReviewForm(data)

    if not form.is_valid():
        return JsonResponse(
            {"errors": form.errors.get_json_data()},
            status=400,
        )

    try:
        with transaction.atomic():
            item = (
                OrderItem.objects
                .select_for_update()
                .select_related("order")
                .get(
                    pk=item_id,
                    order__user=request.user,
                )
            )

            if item.order.status != Order.Status.COMPLETED:
                return JsonResponse(
                    {
                        "message": (
                            "Review hanya bisa dibuat "
                            "setelah pesanan selesai."
                        )
                    },
                    status=409,
                )

            if Review.objects.filter(order_item=item).exists():
                return JsonResponse(
                    {
                        "message": (
                            "Item pesanan ini sudah diberi review."
                        )
                    },
                    status=409,
                )

            review = form.save(commit=False)
            review.order_item = item
            review.save()

            result = review_data(review)

    except OrderItem.DoesNotExist:
        return JsonResponse(
            {"message": "Item pesanan tidak ditemukan."},
            status=404,
        )

    except IntegrityError:
        return JsonResponse(
            {
                "message": (
                    "Review belum bisa disimpan. "
                    "Muat ulang lalu coba lagi."
                )
            },
            status=409,
        )

    return JsonResponse(
        {
            "message": "Review berhasil ditambahkan.",
            "review": result,
        },
        status=201,
    )