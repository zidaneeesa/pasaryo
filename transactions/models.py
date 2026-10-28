from django.db import models
from django.conf import settings


class ShippingMethod(models.Model):
    name = models.CharField(max_length=100)
    estimated_days = models.CharField(max_length=20)
    base_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "shipping_methods"

    def __str__(self):
        return self.name


class PaymentMethod(models.Model):
    name = models.CharField(max_length=100)
    channel_provider = models.CharField(max_length=100)
    service_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "payment_methods"

    def __str__(self):
        return self.name

class DiscountType(models.TextChoices):
    PERCENTAGE = "percentage", "Persentase"
    FIXED = "fixed", "Nominal"


class PromoCode(models.Model):
    code = models.CharField(max_length=50, unique=True)

    discount_type = models.CharField(
        max_length=10,
        choices=DiscountType.choices,
    )
    discount_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    max_discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    min_order_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    quota_total = models.PositiveIntegerField()
    quota_per_user = models.PositiveIntegerField(default=1)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "promo_codes"

    def __str__(self):
        return self.code


class Order(models.Model):
    class Status(models.TextChoices):
        TO_PAY = "to_pay", "To Pay"
        PROCESSING = "processing", "Processing"
        SHIPPED = "shipped", "Shipped"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    order_number = models.CharField(
        max_length=50,
        unique=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    shipping_method = models.ForeignKey(
        ShippingMethod,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    promo_code = models.ForeignKey(
        PromoCode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )

    shipping_address_snapshot = models.TextField()

    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    shipping_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    service_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.TO_PAY,
    )
    estimated_delivery_from = models.DateField(
        null=True,
        blank=True,
    )
    estimated_delivery_to = models.DateField(
        null=True,
        blank=True,
    )
    payment_due_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "orders"
        ordering = ["-created_at"]

    def __str__(self):
        return self.order_number
class OrderTracking(models.Model):
    class StatusCode(models.TextChoices):
        ORDER_PLACED = "order_placed", "Order Placed"
        PAYMENT_CONFIRMED = "payment_confirmed", "Payment Confirmed"
        PROCESSING = "processing", "Processing"
        SHIPPED = "shipped", "Shipped"
        IN_TRANSIT = "in_transit", "In Transit"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    order = models.ForeignKey(
        "Order",
        on_delete=models.CASCADE,
        related_name="trackings",
    )
    status_code = models.CharField(
        max_length=30,
        choices=StatusCode.choices,
    )
    description = models.CharField(
        max_length=255,
        blank=True,
    )
    event_time = models.DateTimeField(
        null=True,
        blank=True,
    )
    expected_time = models.DateTimeField(
        null=True,
        blank=True,
    )
    is_completed = models.BooleanField(default=False)

    class Meta:
        db_table = "order_trackings"
        ordering = ["event_time"]

class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"
        EXPIRED = "EXPIRED", "Expired"

    order = models.ForeignKey(
        "Order",
        on_delete=models.CASCADE,
        related_name="payments",
    )
    payment_method = models.ForeignKey(
        "PaymentMethod",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    payment_reference = models.CharField(
        max_length=100,
        unique=True,
    )
    payment_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    payment_status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    paid_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    payment_url = models.URLField(
        max_length=500,
        blank=True,
    )

    class Meta:
        db_table = "payments"

    def __str__(self):
        return self.payment_reference