"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path

from . import frontend_views

urlpatterns = [
    path("", frontend_views.catalog_page, name="page-catalog"),
    path(
        "produk/<int:product_id>/",
        frontend_views.product_detail_page,
        name="page-product-detail",
    ),
    path(
        "wishlist-saya/",
        frontend_views.wishlist_page,
        name="page-wishlist",
    ),
    path("keranjang/", frontend_views.cart_page, name="page-cart"),
    path("pesanan/", frontend_views.orders_page, name="page-orders"),
    path(
        "pesanan/<int:order_id>/",
        frontend_views.order_detail_page,
        name="page-order-detail",
    ),
    path("akun/", frontend_views.account_page, name="page-account"),
    path(
        "frontend-api/products/<int:product_id>/reviews/",
        frontend_views.product_reviews_api,
        name="frontend-product-reviews",
    ),
    path(
        "frontend-api/orders/<int:order_id>/reviews/",
        frontend_views.order_reviews_api,
        name="frontend-order-reviews",
    ),
    path("admin/", admin.site.urls),
    path("api/", include("transactions.urls")),
    path('accounts/', include('accounts.urls')),
    path("catalog/", include("catalog.urls")),
    path("wishlist/", include("wishlist.urls")),
    path("reviews/", include("transactions.review_urls")),
]
