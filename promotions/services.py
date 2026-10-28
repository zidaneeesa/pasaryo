from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Prefetch
from django.utils import timezone

from .models import EventProduct


CENT = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100")


def with_product_promotions(queryset):
    return queryset.prefetch_related(
        Prefetch(
            "discounts",
            to_attr="pricing_discounts",
        ),
        Prefetch(
            "event_products",
            queryset=EventProduct.objects.select_related("event"),
            to_attr="pricing_event_products",
        ),
    )


def get_product_pricing(product, *, at=None):
    at = timezone.now() if at is None else at
    price = Decimal(str(product.price)).quantize(CENT)
    candidates = []

    discounts = getattr(product, "pricing_discounts", None)
    if discounts is None:
        discounts = product.discounts.all()

    event_products = getattr(product, "pricing_event_products", None)
    if event_products is None:
        event_products = product.event_products.select_related("event")

    for discount in discounts:
        if (
            discount.start_date <= at < discount.end_date
            and discount.discount_value > ZERO
        ):
            candidates.append((
                discount.discount_value,
                0,  # Prioritas diskon reguler
                discount.pk,
                {
                    "source": "discount",
                    "id": discount.pk,
                },
            ))

    for event_product in event_products:
        event = event_product.event

        if not event.start_date <= at < event.end_date:
            continue

        percentage = (
            event.discount_value
            if event_product.discount_value is None
            else event_product.discount_value
        )

        if percentage >= ZERO:
            candidates.append((
                percentage,
                1,  # Event diprioritaskan di atas reguler
                event_product.pk,
                {
                    "source": "event",
                    "id": event.pk,
                    "event_product_id": event_product.pk,
                    "name": event.name,
                },
            ))

    winner = max(
        candidates,
        key=lambda item: (item[1], item[0], -item[2]),
        default=(ZERO, 0, 0, None),
    )

    percentage = winner[0].quantize(CENT)
    amount = (price * percentage / HUNDRED).quantize(
        CENT,
        rounding=ROUND_HALF_UP,
    )

    return {
        "price": price,
        "discount_percentage": percentage,
        "discount_amount": amount,
        "final_price": price - amount,
        "promotion": winner[3],
    }