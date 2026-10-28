from django.core.paginator import EmptyPage, Paginator
from django.db import IntegrityError, transaction
from django.db.models import Avg
from django.http import JsonResponse
from django.views.decorators.http import (
    require_GET,
    require_http_methods,
)

from accounts.views import read_json
from catalog.models import Product

from .models import Order, OrderItem, Review
from .review_forms import ReviewForm, ReviewPageForm


def review_queryset():
    return Review.objects.select_related(
        "order_item__order__user",
        "order_item__product_variant",
    ).order_by("-created_at", "-pk")


def review_data(review, *, public=False):
    item = review.order_item

    data = {
        "id": review.pk,
        "rating": review.rating,
        "comment": review.comment,
        "created_at": review.created_at.isoformat(),
    }

    if public:
        data["author"] = item.order.user.full_name
    else:
        variant = item.product_variant

        data.update({
            "order_item_id": item.pk,
            "product_id": variant.product_id if variant else None,
            "product_name": item.product_name_snapshot,
            "variant_name": item.variant_name_snapshot,
        })

    return data


def paginated_reviews(request, queryset, *, public=False):
    form = ReviewPageForm(request.GET)

    if not form.is_valid():
        return JsonResponse(
            {"errors": form.errors.get_json_data()},
            status=400,
        )

    paginator = Paginator(
        queryset,
        form.cleaned_data["page_size"] or 20,
    )

    try:
        page = paginator.page(form.cleaned_data["page"] or 1)
    except EmptyPage:
        return JsonResponse(
            {"message": "Halaman tidak ditemukan."},
            status=404,
        )

    data = {
        "count": paginator.count,
        "page": page.number,
        "page_size": paginator.per_page,
        "total_pages": paginator.num_pages,
        "results": [
            review_data(item, public=public)
            for item in page.object_list
        ],
    }

    if public:
        average = queryset.aggregate(
            value=Avg("rating")
        )["value"]

        data["average_rating"] = (
            round(average, 2)
            if average is not None
            else None
        )

    return JsonResponse(data)


@require_http_methods(["GET", "POST"])
def review_list_view(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"message": "Silakan login terlebih dahulu."},
            status=401,
        )

    if request.method == "GET":
        reviews = review_queryset().filter(
            order_item__order__user=request.user,
        )
        return paginated_reviews(request, reviews)

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


@require_http_methods(["GET", "PATCH", "DELETE"])
def review_detail_view(request, review_id):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"message": "Silakan login terlebih dahulu."},
            status=401,
        )

    if request.method == "GET":
        try:
            review = review_queryset().get(
                pk=review_id,
                order_item__order__user=request.user,
            )
        except Review.DoesNotExist:
            return JsonResponse(
                {"message": "Review tidak ditemukan."},
                status=404,
            )

        return JsonResponse({
            "review": review_data(review),
        })

    if request.method == "PATCH":
        data = read_json(request)

        if data is None:
            return JsonResponse(
                {"message": "Body harus berupa objek JSON."},
                status=400,
            )

        if not data or set(data) - {"rating", "comment"}:
            return JsonResponse(
                {
                    "message": (
                        "Kirim rating dan/atau comment saja."
                    )
                },
                status=400,
            )

    try:
        with transaction.atomic():
            review = (
                Review.objects
                .select_for_update()
                .select_related("order_item__order")
                .get(
                    pk=review_id,
                    order_item__order__user=request.user,
                )
            )

            if request.method == "DELETE":
                review.delete()

                return JsonResponse({
                    "message": "Review berhasil dihapus.",
                })

            if review.order_item.order.status != Order.Status.COMPLETED:
                return JsonResponse(
                    {
                        "message": (
                            "Review hanya bisa diubah "
                            "untuk pesanan yang selesai."
                        )
                    },
                    status=409,
                )

            values = {
                "rating": review.rating,
                "comment": review.comment,
            }
            values.update(data)

            form = ReviewForm(values, instance=review)

            if not form.is_valid():
                return JsonResponse(
                    {"errors": form.errors.get_json_data()},
                    status=400,
                )

            review = form.save(commit=False)
            review.save(update_fields=["rating", "comment"])

            result = review_data(review)

    except Review.DoesNotExist:
        return JsonResponse(
            {"message": "Review tidak ditemukan."},
            status=404,
        )

    except IntegrityError:
        return JsonResponse(
            {
                "message": (
                    "Perubahan review belum bisa disimpan. "
                    "Silakan ulangi."
                )
            },
            status=409,
        )

    return JsonResponse({
        "message": "Review berhasil diperbarui.",
        "review": result,
    })


@require_GET
def product_reviews_view(request, product_id):
    if not Product.objects.filter(pk=product_id).exists():
        return JsonResponse(
            {"message": "Produk tidak ditemukan."},
            status=404,
        )

    reviews = review_queryset().filter(
        order_item__product_variant__product_id=product_id,
    )

    return paginated_reviews(
        request,
        reviews,
        public=True,
    )