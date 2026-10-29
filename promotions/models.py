from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


# Enum tipe diskon, saat ini hanya mendukung persentase
class DiscountType(models.TextChoices):
    PERCENTAGE = "percentage", "Persentase"


# Diskon langsung per produk dengan periode waktu tertentu (dalam persen)
class Discount(models.Model):
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="discounts",
    )
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    discount_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    class Meta:
        db_table = "discount"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gt=models.F("start_date")),
                name="discount_valid_dates",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    discount_value__gte=0,
                    discount_value__lte=100,
                ),
                name="discount_valid_percent",
            ),
        ]

    def __str__(self):
        return f"Produk {self.product_id}: {self.discount_value}%"


# Event promosi (misal: Flash Sale, Harbolnas) yang bisa mencakup banyak produk
class Event(models.Model):
    name = models.CharField(max_length=150)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    discount_type = models.CharField(
        max_length=10,
        choices=DiscountType.choices,
        default=DiscountType.PERCENTAGE,
    )
    discount_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    products = models.ManyToManyField(
        "catalog.Product",
        through="EventProduct",
        related_name="events",
    )

    class Meta:
        db_table = "event"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gt=models.F("start_date")),
                name="event_valid_dates",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    discount_value__gte=0,
                    discount_value__lte=100,
                ),
                name="event_valid_percent",
            ),
            models.CheckConstraint(
                condition=models.Q(discount_type="percentage"),
                name="event_percentage_type",
            ),
        ]

    def __str__(self):
        return self.name


# Tabel pivot event-produk, bisa override diskon event untuk produk tertentu
class EventProduct(models.Model):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="event_products",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="event_products",
    )
    discount_type = models.CharField(
        max_length=10,
        choices=DiscountType.choices,
        null=True,
        blank=True,
    )
    discount_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    class Meta:
        db_table = "event_product"
        constraints = [
            models.UniqueConstraint(
                fields=["event", "product"],
                name="unique_event_product",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        discount_type__isnull=True,
                        discount_value__isnull=True,
                    )
                    | models.Q(
                        discount_type__isnull=False,
                        discount_type="percentage",
                        discount_value__isnull=False,
                        discount_value__gte=0,
                        discount_value__lte=100,
                    )
                ),
                name="event_product_valid_override",
            ),
        ]

    def __str__(self):
        return f"Event {self.event_id} - Produk {self.product_id}"