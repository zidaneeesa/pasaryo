from django.db import models
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator


# Metode pengiriman (misal: JNE REG, SiCepat, dll) beserta estimasi dan biaya
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


# Metode pembayaran (misal: BCA VA, GoPay, dll) beserta service fee
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

# Enum tipe diskon untuk promo code: persentase atau nominal tetap
class DiscountType(models.TextChoices):
    PERCENTAGE = "percentage", "Persentase"
    FIXED = "fixed", "Nominal"


# Kode promo yang bisa dipakai saat checkout untuk mendapatkan diskon
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


# Pesanan utama, menyimpan ringkasan harga, status, dan relasi ke user/shipping/promo
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
    checkout_key = models.UUIDField(
        null=True,
        blank=True,
        editable=False,
    )
    checkout_payload = models.JSONField(
        default=dict,
        blank=True,
        editable=False,
    )
    stock_deducted = models.BooleanField(
        default=False,
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "orders"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "checkout_key"],
                name="unique_checkout_key_per_user",
            ),
        ]

    def __str__(self):
        return self.order_number

# Riwayat tracking pesanan, mencatat setiap perubahan status pengiriman
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

# Pembayaran untuk pesanan, satu pesanan bisa punya beberapa percobaan bayar
class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"
        EXPIRED = "EXPIRED", "Expired"
        CANCELLED = "CANCELLED", "Cancelled"

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
        
# Keranjang belanja user, tiap item merujuk ke varian produk tertentu
class Cart(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cart_items",
    )
    product_variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.CASCADE,
        related_name="cart_items",
    )
    quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )

    class Meta:
        db_table = "carts"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product_variant"],
                name="unique_cart_item",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="cart_quantity_gte_one",
            ),
        ]

    def __str__(self):
        return (
            f"User {self.user_id} - "
            f"Variant {self.product_variant_id} ({self.quantity})"
        )

# Item dalam pesanan, menyimpan snapshot data produk saat checkout
class OrderItem(models.Model):
    order = models.ForeignKey(
        "Order",
        on_delete=models.CASCADE,
        related_name="items",
    )
    product_variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )
    product_name_snapshot = models.CharField(max_length=200)
    variant_name_snapshot = models.CharField(max_length=100)
    sku_snapshot = models.CharField(max_length=64)
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
    )
    price_at_purchase = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        db_table = "order_items"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="order_item_quantity_gte_one",
            ),
            models.CheckConstraint(
                condition=models.Q(price_at_purchase__gte=0),
                name="order_item_price_nonnegative",
            ),
        ]

    # Menghitung total harga per baris (harga × jumlah)
    @property
    def line_total(self):
        return self.price_at_purchase * self.quantity

    def __str__(self):
        return f"{self.order_id} - {self.product_name_snapshot}"


# Review/ulasan dari pembeli untuk item pesanan yang sudah diterima (rating 1-5)
class Review(models.Model):
    order_item = models.OneToOneField(
        "OrderItem",
        on_delete=models.CASCADE,
        related_name="review",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(5),
        ],
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "reviews"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    rating__gte=1,
                    rating__lte=5,
                ),
                name="review_rating_between_1_and_5",
            ),
        ]

    def __str__(self):
        return f"Review item {self.order_item_id}: {self.rating}/5"