from django.urls import path
from . import address_views

from . import views

app_name = "accounts"

urlpatterns = [
    path("csrf/", views.csrf_view, name="csrf"),
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("me/", views.me_view, name="me"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile_update_view, name="profile"),
    path(
        "change-password/",
        views.password_change_view,
        name="change_password",
    ),
    path(
        "addresses/",
        address_views.address_list_view,
        name="address_list",
    ),
    path(
        "addresses/<int:address_id>/",
        address_views.address_detail_view,
        name="address_detail",
    ),
    path(
        "addresses/<int:address_id>/main/",
        address_views.address_main_view,
        name="address_main",
    ),
]