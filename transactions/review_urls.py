from django.urls import path

from . import review_views

app_name = "reviews"

urlpatterns = [
    path(
        "",
        review_views.review_create_view,
        name="create",
    ),
]