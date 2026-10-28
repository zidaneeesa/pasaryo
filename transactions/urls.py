from django.urls import path

from . import views

app_name = "transactions"

urlpatterns = [
    path(
        "shipping-methods/",
        views.shipping_method_list,
        name="shipping-method-list",
    ),
    path(
        "payment-methods/",
        views.payment_method_list,
        name="payment-method-list",
    ),
    path(
        "orders/",
        views.order_history,
        name="order-history",
    ),
    path(
        "orders/<int:order_id>/tracking/",
        views.order_tracking,
        name="order-tracking",
    ),
    path(
        "orders/<int:order_id>/",
        views.order_detail,
        name="order-detail",
    ),
    path(
        "orders/<int:order_id>/payments/",
        views.payment_create,
        name="payment-create",
    ),
    path(
        "cart/",
        views.cart_collection,
        name="cart",
    ),
    path(
        "cart/<int:cart_item_id>/",
        views.cart_item_detail,
        name="cart-item",
    ),
    path(
        "promo-codes/validate/",
        views.promo_code_validate,
        name="promo-code-validate",
    ),
    path(
        "orders/<int:order_id>/complete/",
        views.order_complete,
        name="order-complete",
    ),
    path("checkout/", views.checkout_create, name="checkout"),
    path(
        "orders/<int:order_id>/cancel/",
        views.order_cancel,
        name="order-cancel",
    ),
]