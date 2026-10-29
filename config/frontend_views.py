from django.db.models import Avg
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET

from transactions.models import Review


def _initials(full_name):
    parts = [p for p in (full_name or "").strip().split() if p]
    if not parts:
        return "PS"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


@ensure_csrf_cookie
@require_GET
def catalog_page(request):
    return render(
        request,
        "pages/catalog.html",
        {"active_nav": "catalog"},
    )


@ensure_csrf_cookie
@require_GET
def product_detail_page(request, product_id):
    return render(
        request,
        "pages/product_detail.html",
        {
            "active_nav": "catalog",
            "product_id": product_id,
        },
    )


@ensure_csrf_cookie
@require_GET
def wishlist_page(request):
    return render(
        request,
        "pages/wishlist.html",
        {"active_nav": "wishlist"},
    )


@ensure_csrf_cookie
@require_GET
def cart_page(request):
    return render(
        request,
        "pages/cart.html",
        {"active_nav": "cart"},
    )


@ensure_csrf_cookie
@require_GET
def orders_page(request):
    return render(
        request,
        "pages/orders.html",
        {"active_nav": "orders"},
    )


@ensure_csrf_cookie
@require_GET
def order_detail_page(request, order_id):
    return render(
        request,
        "pages/order_detail.html",
        {
            "active_nav": "orders",
            "order_id": order_id,
        },
    )


@ensure_csrf_cookie
@require_GET
def account_page(request):
    return render(
        request,
        "pages/account.html",
        {"active_nav": "account"},
    )


@require_GET
def product_reviews_api(request, product_id):
    reviews_qs = (
        Review.objects.select_related(
            "order_item",
            "order_item__order",
            "order_item__order__user",
        )
        .filter(order_item__product_variant__product_id=product_id)
        .order_by("-created_at", "-id")
    )
    agg = reviews_qs.aggregate(avg_rating=Avg("rating"))
    avg_val = agg["avg_rating"]
    results = []
    for rev in reviews_qs[:50]:
        user = rev.order_item.order.user
        full_name = getattr(user, "full_name", "") or "Pembeli Pasaryo"
        results.append(
            {
                "id": rev.pk,
                "order_item_id": rev.order_item_id,
                "rating": rev.rating,
                "comment": rev.comment,
                "variant_name": rev.order_item.variant_name_snapshot,
                "reviewer_name": full_name,
                "reviewer_initials": _initials(full_name),
                "created_at": rev.created_at.isoformat(),
            }
        )
    return JsonResponse(
        {
            "count": len(results),
            "average_rating": round(float(avg_val), 1) if avg_val is not None else None,
            "results": results,
        }
    )


@require_GET
def order_reviews_api(request, order_id):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"message": "Silakan login terlebih dahulu."},
            status=401,
        )
    reviews = Review.objects.filter(
        order_item__order_id=order_id,
        order_item__order__user=request.user,
    )
    by_item = {
        str(rev.order_item_id): {
            "id": rev.pk,
            "order_item_id": rev.order_item_id,
            "rating": rev.rating,
            "comment": rev.comment,
            "created_at": rev.created_at.isoformat(),
        }
        for rev in reviews
    }
    return JsonResponse({"reviews_by_item": by_item})

