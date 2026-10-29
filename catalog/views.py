from django.core.paginator import EmptyPage, Paginator
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .forms import ProductFilterForm
from .models import Brand, Category, Product

from promotions.services import (
    get_product_pricing,
    with_product_promotions,
)


# Menyiapkan queryset produk dengan relasi kategori, brand, gambar, dan data promosi
def product_queryset():
    products = Product.objects.select_related(
        "category", "brand"
    ).prefetch_related("images")

    return with_product_promotions(products)


# Mengubah objek Product menjadi dict untuk response JSON (detail=True untuk info lengkap)
def product_data(product, detail=False):
    images = list(product.images.all())
    pricing = get_product_pricing(product)

    data = {
        "id": product.pk,
        "name": product.name,
        "price": str(product.price),
        "origin_city": product.origin_city,
        "category": {
            "id": product.category_id,
            "name": product.category.name,
        },
        "brand": {
            "id": product.brand_id,
            "name": product.brand.name,
        },
        "image_url": images[0].image_url if images else None,
        "discount_percentage": str(pricing["discount_percentage"]),
        "discount_amount": str(pricing["discount_amount"]),
        "final_price": str(pricing["final_price"]),
        "promotion": pricing["promotion"],
    }

    if detail:
        data.update({
            "description": product.description,
            "specifications": product.specifications,
            "images": [
                {
                    "id": image.pk,
                    "image_url": image.image_url,
                    "sort_order": image.sort_order,
                }
                for image in images
            ],
            "variants": [
                {
                    "id": variant.pk,
                    "color_name": variant.color_name,
                    "sku": variant.sku,
                    "stock": variant.stock,
                }
                for variant in product.variants.all()
            ],
        })

    return data


# Mengembalikan daftar semua kategori produk
@require_GET
def category_list_view(request):
    categories = Category.objects.order_by(
        "name", "pk"
    ).values("id", "name")

    return JsonResponse({"results": list(categories)})


# Mengembalikan daftar semua brand produk
@require_GET
def brand_list_view(request):
    brands = Brand.objects.order_by(
        "name", "pk"
    ).values("id", "name")

    return JsonResponse({"results": list(brands)})


# Mengembalikan daftar produk dengan filter, sorting, dan paginasi
@require_GET
def product_list_view(request):
    form = ProductFilterForm(request.GET)

    if not form.is_valid():
        return JsonResponse(
            {"errors": form.errors.get_json_data()},
            status=400,
        )

    data = form.cleaned_data
    products = product_queryset()

    if data["q"]:
        products = products.filter(name__icontains=data["q"])

    if data["category_id"] is not None:
        products = products.filter(category_id=data["category_id"])

    if data["brand_id"] is not None:
        products = products.filter(brand_id=data["brand_id"])

    if data["min_price"] is not None:
        products = products.filter(price__gte=data["min_price"])

    if data["max_price"] is not None:
        products = products.filter(price__lte=data["max_price"])

    if data["origin_city"]:
        products = products.filter(
            origin_city__icontains=data["origin_city"]
        )

    products = products.order_by(data["sort"] or "-id", "pk")
    paginator = Paginator(products, data["page_size"] or 20)

    try:
        page = paginator.page(data["page"] or 1)
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
            product_data(product)
            for product in page.object_list
        ],
    })


# Mengembalikan detail satu produk berdasarkan ID (termasuk varian dan gambar)
@require_GET
def product_detail_view(request, product_id):
    try:
        product = product_queryset().prefetch_related(
            "variants"
        ).get(pk=product_id)
    except Product.DoesNotExist:
        return JsonResponse(
            {"message": "Produk tidak ditemukan."},
            status=404,
        )

    return JsonResponse({
        "product": product_data(product, detail=True)
    })