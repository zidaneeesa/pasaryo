from django.conf import settings
from django.db import models


# Wishlist user, satu user hanya bisa menambahkan satu produk sekali (unique constraint)
class Wishlist(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wishlists",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="wishlisted_by",
    )

    class Meta:
        db_table = "wishlists"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"],
                name="unique_wishlist_item",
            ),
        ]