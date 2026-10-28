from django.urls import path

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
]