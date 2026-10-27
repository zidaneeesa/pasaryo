from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class DiscountType(models.TextChoices):
    PERCENTAGE = "percentage", "Persentase"
    FIXED = "fixed", "Fixed"


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email wajib diisi")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        USER = "user", "User"

    full_name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    # `password` sudah disediakan AbstractBaseUser (otomatis di-hash).
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.USER)
    date_of_birth = models.DateField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        db_table = "users"

    def __str__(self):
        return self.email


class UserAddress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=50)
    recipient_name = models.CharField(max_length=150)
    recipient_phone = models.CharField(max_length=20)
    street_address = models.TextField()
    subdistrict = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    province = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=10)
    is_main = models.BooleanField(default=False)

    class Meta:
        db_table = "user_addresses"
        constraints = [
            # Satu user hanya boleh punya satu alamat utama.
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_main=True),
                name="unique_main_address_per_user",
            ),
        ]

    def __str__(self):
        return f"{self.label} - {self.recipient_name}"


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

class Brand(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = "brands"

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = "categories"
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="products")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    specifications = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    origin_city = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "products"

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image_url = models.URLField(max_length=500)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "product_images"
        ordering = ["sort_order"]


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    color_name = models.CharField(max_length=50)
    stock = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=64, unique=True)

    class Meta:
        db_table = "product_variants"

    def __str__(self):
        return f"{self.product.name} - {self.color_name}"


# ---------------------------------------------------------------------------
# Promotions
# ---------------------------------------------------------------------------

class Event(models.Model):
    name = models.CharField(max_length=150)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices)
    discount_value = models.DecimalField(max_digits=12, decimal_places=2)
    products = models.ManyToManyField(Product, through="EventProduct", related_name="events")

    class Meta:
        db_table = "event"

    def __str__(self):
        return self.name


class EventProduct(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="event_products")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="event_products")
    # Kosong = ikut diskon default dari Event.
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices, null=True, blank=True)
    discount_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = "event_product"
        constraints = [
            models.UniqueConstraint(fields=["event", "product"], name="unique_event_product"),
        ]


class Discount(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="discounts")
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    discount_value = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = "discount"


class PromoCode(models.Model):
    code = models.CharField(max_length=50, unique=True)
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices)
    discount_value = models.DecimalField(max_digits=12, decimal_places=2)
    max_discount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    min_order_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    quota_total = models.PositiveIntegerField()
    quota_per_user = models.PositiveIntegerField(default=1)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "promo_codes"

    def __str__(self):
        return self.code


# ---------------------------------------------------------------------------
# Cart & Wishlist
# ---------------------------------------------------------------------------

class Cart(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="cart_items")
    product_variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "carts"
        constraints = [
            models.UniqueConstraint(fields=["user", "product_variant"], name="unique_cart_item"),
        ]


class Wishlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="wishlists")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlisted_by")

    class Meta:
        db_table = "wishlists"
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="unique_wishlist_item"),
        ]


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

class ShippingMethod(models.Model):
    name = models.CharField(max_length=100)
    estimated_days = models.CharField(max_length=20)
    base_cost = models.DecimalField(max_digits=12, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "shipping_methods"

    def __str__(self):
        return self.name


class Order(models.Model):
    class Status(models.TextChoices):
        TO_PAY = "to_pay", "To Pay"
        PROCESSING = "processing", "Processing"
        SHIPPED = "shipped", "Shipped"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    order_number = models.CharField(max_length=50, unique=True)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="orders")
    shipping_method = models.ForeignKey(ShippingMethod, on_delete=models.PROTECT, related_name="orders")
    promo_code = models.ForeignKey(
        PromoCode, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )
    shipping_address_snapshot = models.TextField()
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    shipping_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    service_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TO_PAY)
    estimated_delivery_from = models.DateField(null=True, blank=True)
    estimated_delivery_to = models.DateField(null=True, blank=True)
    payment_due_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "orders"
        ordering = ["-created_at"]

    def __str__(self):
        return self.order_number


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    # SET_NULL: data pembelian tetap aman lewat kolom snapshot walau varian dihapus.
    product_variant = models.ForeignKey(
        ProductVariant, on_delete=models.SET_NULL, null=True, related_name="order_items"
    )
    product_name_snapshot = models.CharField(max_length=200)
    variant_name_snapshot = models.CharField(max_length=100)
    sku_snapshot = models.CharField(max_length=64)
    quantity = models.PositiveIntegerField()
    price_at_purchase = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = "order_items"


class OrderTracking(models.Model):
    class StatusCode(models.TextChoices):
        ORDER_PLACED = "order_placed", "Order Placed"
        PAYMENT_CONFIRMED = "payment_confirmed", "Payment Confirmed"
        PROCESSING = "processing", "Processing"
        SHIPPED = "shipped", "Shipped"
        IN_TRANSIT = "in_transit", "In Transit"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="trackings")
    status_code = models.CharField(max_length=30, choices=StatusCode.choices)
    description = models.CharField(max_length=255, blank=True)
    event_time = models.DateTimeField(null=True, blank=True)
    expected_time = models.DateTimeField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)

    class Meta:
        db_table = "order_trackings"
        ordering = ["event_time"]


class Review(models.Model):
    # OneToOne: satu item pesanan hanya bisa di-review sekali.
    order_item = models.OneToOneField(OrderItem, on_delete=models.CASCADE, related_name="review")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "reviews"


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

class PaymentMethod(models.Model):
    name = models.CharField(max_length=100)
    channel_provider = models.CharField(max_length=100)
    service_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "payment_methods"

    def __str__(self):
        return self.name


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"
        EXPIRED = "EXPIRED", "Expired"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, related_name="payments")
    payment_reference = models.CharField(max_length=100, unique=True)
    payment_amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    expires_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_url = models.URLField(max_length=500, blank=True)

    class Meta:
        db_table = "payments"