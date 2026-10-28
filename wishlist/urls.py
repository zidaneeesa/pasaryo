from django.urls import path
from . import views

app_name = "wishlist"

urlpatterns = [
    path(
        "",
        views.wishlist_list_view,
        name="list",
    ),
    path(
        "<int:product_id>/",
        views.wishlist_delete_view,
        name="delete",
    ),
]