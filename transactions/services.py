from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import transaction

from .models import DiscountType, Order, Payment, PaymentMethod, PromoCode


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

@transaction.atomic
def create_payment_transaction(*, user, order_id, payment_method_id):
    if (
        not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
        or not getattr(user, "pk", None)
    ):
        raise ValidationError("Silakan login terlebih dahulu.")

    order = (
        Order.objects
        .select_for_update()
        .filter(pk=order_id, user=user)
        .first()
    )

    if order is None:
        raise ValidationError("Pesanan tidak ditemukan.")

    if order.status != Order.Status.TO_PAY:
        raise ValidationError(
            "Pesanan tidak dalam status menunggu pembayaran."
        )

    payment_method = (
        PaymentMethod.objects
        .select_for_update()
        .filter(pk=payment_method_id, is_active=True)
        .first()
    )

    if payment_method is None:
        raise ValidationError("Metode pembayaran tidak tersedia.")

    # Checkout nanti harus menghitung biaya memakai metode yang dipilih.
    if order.service_fee != payment_method.service_fee:
        raise ValidationError(
            "Biaya layanan pesanan tidak sesuai metode pembayaran."
        )

    expected_total = (
        order.subtotal
        + order.shipping_fee
        + order.service_fee
        - order.discount_amount
    )

    if (
        order.subtotal <= 0
        or order.shipping_fee < 0
        or order.service_fee < 0
        or order.discount_amount < 0
        or order.discount_amount > order.subtotal
        or order.total_amount <= 0
        or order.total_amount != expected_total
    ):
        raise ValidationError("Rincian total pesanan tidak valid.")

    if order.payments.filter(
        payment_status=Payment.Status.SUCCESS
    ).exists():
        raise ValidationError("Pesanan sudah memiliki pembayaran sukses.")

    # Membuat percobaan baru tidak memperpanjang batas waktu pesanan.
    if (
        order.payment_due_at is None
        or order.payment_due_at <= timezone.now()
    ):
        raise ValidationError(
            "Batas waktu pembayaran belum tersedia atau sudah kedaluwarsa."
        )

    return Payment.objects.create(
        order=order,
        payment_method=payment_method,
        payment_reference=f"PAY-{uuid4().hex.upper()}",
        payment_amount=order.total_amount,
        payment_status=Payment.Status.PENDING,
        expires_at=order.payment_due_at,
    )