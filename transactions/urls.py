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
]