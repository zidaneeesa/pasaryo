from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path(
        "categories/",
        views.category_list_view,
        name="category_list",
    ),
    path(
        "brands/",
        views.brand_list_view,
        name="brand_list",
    ),
    path(
        "products/",
        views.product_list_view,
        name="product_list",
    ),
    path(
        "products/<int:product_id>/",
        views.product_detail_view,
        name="product_detail",
    ),
]