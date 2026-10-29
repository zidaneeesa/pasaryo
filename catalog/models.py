from django.db import models


# Kategori produk (misal: Elektronik, Fashion, dll)
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = "categories"
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


# Brand/merek produk (misal: Samsung, Nike, dll)
class Brand(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = "brands"

    def __str__(self):
        return self.name


# Produk yang dijual, terhubung ke satu kategori dan satu brand
class Product(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        related_name="products",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    specifications = models.TextField(blank=True)
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    origin_city = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "products"

    def __str__(self):
        return self.name


# Gambar produk, satu produk bisa punya banyak gambar, diurutkan via sort_order
class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image_url = models.URLField(max_length=500)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "product_images"
        ordering = ["sort_order"]


# Varian produk berdasarkan warna, tiap varian punya SKU unik dan stok sendiri
class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    color_name = models.CharField(max_length=50)
    stock = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=64, unique=True)

    class Meta:
        db_table = "product_variants"

    def __str__(self):
        return f"{self.product.name} - {self.color_name}"