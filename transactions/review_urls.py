from django.urls import path

from . import review_views

app_name = "reviews"

urlpatterns = [
    path(
        "",
        review_views.review_list_view,
        name="list",
    ),
    path(
        "products/<int:product_id>/",
        review_views.product_reviews_view,
        name="product",
    ),
    path(
        "<int:review_id>/",
        review_views.review_detail_view,
        name="detail",
    ),
]