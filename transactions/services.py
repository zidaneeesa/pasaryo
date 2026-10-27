from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import DiscountType, Order, PromoCode


CENT = Decimal("0.01")
MAX_SUBTOTAL = Decimal("9999999999.99")


def validate_promo_code(*, user, code, subtotal):
    """
    subtotal harus berupa Decimal hasil perhitungan server.
    Mengembalikan: (objek promo, nominal potongan).
    """
    if (
        not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
        or not getattr(user, "pk", None)
    ):
        raise ValidationError("Silakan login terlebih dahulu.")

    if not isinstance(code, str):
        raise ValidationError("Kode promo wajib berupa teks.")

    code = code.strip()

    if not code or len(code) > 50:
        raise ValidationError("Kode promo tidak valid.")

    if (
        not isinstance(subtotal, Decimal)
        or not subtotal.is_finite()
        or subtotal <= 0
        or subtotal > MAX_SUBTOTAL
    ):
        raise ValidationError("Subtotal tidak valid.")

    if subtotal != subtotal.quantize(CENT):
        raise ValidationError("Subtotal maksimal dua angka desimal.")

    try:
        promo = PromoCode.objects.get(code=code)
    except PromoCode.DoesNotExist:
        raise ValidationError("Kode promo tidak ditemukan.") from None

    now = timezone.now()

    if not promo.is_active:
        raise ValidationError("Kode promo tidak aktif.")

    if promo.expires_at <= now:
        raise ValidationError("Kode promo sudah kedaluwarsa.")

    if subtotal < promo.min_order_amount:
        raise ValidationError(
            "Subtotal belum memenuhi minimum belanja promo."
        )

    if (
        promo.discount_value <= 0
        or promo.min_order_amount < 0
        or (
            promo.max_discount is not None
            and promo.max_discount <= 0
        )
    ):
        raise ValidationError("Nilai diskon promo tidak valid.")

    if promo.discount_type == DiscountType.PERCENTAGE:
        if promo.discount_value > 100:
            raise ValidationError(
                "Persentase diskon tidak boleh melebihi 100."
            )

        discount = (
            subtotal * promo.discount_value / Decimal("100")
        )

    elif promo.discount_type == DiscountType.FIXED:
        discount = promo.discount_value

    else:
        raise ValidationError("Jenis diskon promo tidak valid.")

    used_orders = (
        Order.objects.filter(promo_code=promo)
        .exclude(status=Order.Status.CANCELLED)
        .exclude(
            status=Order.Status.TO_PAY,
            payment_due_at__lte=now,
        )
    )

    if used_orders.count() >= promo.quota_total:
        raise ValidationError("Kuota promo sudah habis.")

    if (
        used_orders.filter(user=user).count()
        >= promo.quota_per_user
    ):
        raise ValidationError(
            "Batas penggunaan promo untuk akun ini sudah tercapai."
        )

    if promo.max_discount is not None:
        discount = min(discount, promo.max_discount)

    discount = min(discount, subtotal).quantize(
        CENT,
        rounding=ROUND_HALF_UP,
    )

    return promo, discount