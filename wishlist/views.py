from django.core.paginator import EmptyPage, Paginator
from django.db import IntegrityError
from django.db.models import Prefetch
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from accounts.views import read_json
from catalog.models import Product
from catalog.views import product_data, product_queryset

from .forms import WishlistPageForm
from .models import Wishlist


# GET: daftar wishlist user (dengan paginasi), POST: tambah produk ke wishlist
@require_http_methods(["GET", "POST"])
def wishlist_list_view(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"message": "Silakan login terlebih dahulu."},
            status=401,
        )

    if request.method == "GET":
        form = WishlistPageForm(request.GET)
        if not form.is_valid():
            return JsonResponse(
                {"errors": form.errors.get_json_data()},
                status=400,
            )

        items = Wishlist.objects.filter(
            user=request.user
        ).order_by("-pk").prefetch_related(
            Prefetch("product", queryset=product_queryset())
        )

        paginator = Paginator(
            items,
            form.cleaned_data["page_size"] or 20,
        )

        try:
            page = paginator.page(
                form.cleaned_data["page"] or 1
            )
        except EmptyPage:
            return JsonResponse(
                {"message": "Halaman tidak ditemukan."},
                status=404,
            )

        return JsonResponse({
            "count": paginator.count,
            "page": page.number,
            "page_size": paginator.per_page,
            "total_pages": paginator.num_pages,
            "results": [
                {
                    "id": item.pk,
                    "product": product_data(item.product),
                }
                for item in page.object_list
            ],
        })

    data = read_json(request)
    if data is None:
        return JsonResponse(
            {"message": "Body harus berupa objek JSON."},
            status=400,
        )

    product_id = data.get("product_id")
    if type(product_id) is not int or product_id < 1:
        return JsonResponse(
            {
                "message":
                "product_id harus berupa bilangan bulat positif."
            },
            status=400,
        )

    try:
        product = product_queryset().get(pk=product_id)
    except Product.DoesNotExist:
        return JsonResponse(
            {"message": "Produk tidak ditemukan."},
            status=404,
        )

    try:
        item, created = Wishlist.objects.get_or_create(
            user=request.user,
            product=product,
        )
    except IntegrityError:
        return JsonResponse(
            {
                "message":
                "Wishlist belum bisa disimpan. Silakan ulangi."
            },
            status=409,
        )

    return JsonResponse({
        "message": (
            "Produk berhasil ditambahkan ke wishlist."
            if created
            else "Produk sudah ada di wishlist."
        ),
        "item": {
            "id": item.pk,
            "product": product_data(product),
        },
    }, status=201 if created else 200)


# Menghapus produk dari wishlist user berdasarkan product_id
@require_http_methods(["DELETE"])
def wishlist_delete_view(request, product_id):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"message": "Silakan login terlebih dahulu."},
            status=401,
        )

    deleted, _ = Wishlist.objects.filter(
        user=request.user,
        product_id=product_id,
    ).delete()

    if not deleted:
        return JsonResponse(
            {
                "message":
                "Produk tidak ditemukan dalam wishlist Anda."
            },
            status=404,
        )

    return JsonResponse({
        "message": "Produk berhasil dihapus dari wishlist."
    })