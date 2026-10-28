from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID, uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from accounts.models import UserAddress
from catalog.models import Product, ProductVariant

from .models import (
    Cart,
    DiscountType,
    Order,
    OrderItem,
    OrderTracking,
    Payment,
    PaymentMethod,
    PromoCode,
    ShippingMethod,
)

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

@transaction.atomic
def confirm_order_received(*, user, order_id):
    if (
        not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
        or not getattr(user, "pk", None)
    ):
        raise ValidationError("Silakan login terlebih dahulu.")

    # Perubahan dilakukan bersyarat di dalam transaksi.
    # Jika validasi berikutnya gagal, perubahan ini dibatalkan.
    changed = Order.objects.filter(
        pk=order_id,
        user=user,
        status=Order.Status.SHIPPED,
    ).update(status=Order.Status.COMPLETED)

    order = Order.objects.filter(
        pk=order_id,
        user=user,
    ).first()

    if order is None:
        raise ValidationError("Pesanan tidak ditemukan.")

    if changed == 0:
        # Konfirmasi ulang tidak membuat catatan pelacakan baru.
        if order.status == Order.Status.COMPLETED:
            return order

        raise ValidationError(
            "Hanya pesanan berstatus shipped yang bisa "
            "dikonfirmasi diterima."
        )

    has_successful_payment = order.payments.filter(
        payment_status=Payment.Status.SUCCESS,
        payment_amount=order.total_amount,
    ).exists()

    if not has_successful_payment:
        raise ValidationError(
            "Pembayaran pesanan belum berhasil "
            "atau nominalnya tidak sesuai."
        )

    OrderTracking.objects.create(
        order=order,
        status_code=OrderTracking.StatusCode.DELIVERED,
        description="Pesanan diterima dan dikonfirmasi oleh pembeli.",
        event_time=timezone.now(),
        is_completed=True,
    )

    return order

MAX_CART_QUANTITY = 2_147_483_647


def _validate_cart_user(user):
    if (
        not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
        or not getattr(user, "pk", None)
    ):
        raise ValidationError("Silakan login terlebih dahulu.")


def _validate_cart_quantity(quantity):
    if type(quantity) is not int or quantity < 1:
        raise ValidationError(
            "Jumlah harus berupa bilangan bulat minimal 1."
        )

    if quantity > MAX_CART_QUANTITY:
        raise ValidationError("Jumlah terlalu besar.")


def get_cart_items(*, user):
    _validate_cart_user(user)

    return (
        Cart.objects
        .filter(user=user)
        .select_related("product_variant__product")
        .order_by("id")
    )


@transaction.atomic
def add_cart_item(*, user, product_variant_id, quantity=1):
    _validate_cart_user(user)
    _validate_cart_quantity(quantity)

    variant = (
        ProductVariant.objects
        .select_for_update()
        .filter(pk=product_variant_id)
        .first()
    )

    if variant is None:
        raise ValidationError("Varian produk tidak ditemukan.")

    if quantity > variant.stock:
        raise ValidationError(
            "Jumlah yang diminta melebihi stok tersedia."
        )

    item, created = Cart.objects.get_or_create(
        user=user,
        product_variant=variant,
        defaults={"quantity": quantity},
    )

    if not created:
        maximum_existing_quantity = (
            min(variant.stock, MAX_CART_QUANTITY) - quantity
        )

        changed = Cart.objects.filter(
            pk=item.pk,
            user=user,
            quantity__lte=maximum_existing_quantity,
        ).update(quantity=F("quantity") + quantity)

        if changed == 0:
            raise ValidationError(
                "Jumlah total item melebihi stok tersedia."
            )

        item.refresh_from_db()

    return item, created


@transaction.atomic
def set_cart_item_quantity(*, user, cart_item_id, quantity):
    _validate_cart_user(user)
    _validate_cart_quantity(quantity)

    item = Cart.objects.filter(
        pk=cart_item_id,
        user=user,
    ).first()

    if item is None:
        raise ValidationError("Item keranjang tidak ditemukan.")

    variant = (
        ProductVariant.objects
        .select_for_update()
        .filter(pk=item.product_variant_id)
        .first()
    )

    if variant is None:
        raise ValidationError("Item keranjang tidak ditemukan.")

    if quantity > variant.stock:
        raise ValidationError(
            "Jumlah yang diminta melebihi stok tersedia."
        )

    changed = Cart.objects.filter(
        pk=item.pk,
        user=user,
        product_variant_id=variant.pk,
    ).update(quantity=quantity)

    if changed == 0:
        raise ValidationError("Item keranjang tidak ditemukan.")

    item.refresh_from_db()
    return item


def remove_cart_item(*, user, cart_item_id):
    _validate_cart_user(user)

    deleted, _ = Cart.objects.filter(
        pk=cart_item_id,
        user=user,
    ).delete()

    if deleted == 0:
        raise ValidationError("Item keranjang tidak ditemukan.")

def validate_cart_promo_code(*, user, code):
    items = list(get_cart_items(user=user))

    if not items:
        raise ValidationError("Keranjang masih kosong.")

    subtotal = Decimal("0.00")

    for item in items:
        variant = item.product_variant
        product = variant.product

        if item.quantity > variant.stock:
            raise ValidationError(
                f"Stok {product.name} ({variant.color_name}) "
                "tidak mencukupi."
            )

        if product.price < 0:
            raise ValidationError("Harga produk tidak valid.")

        subtotal += product.price * item.quantity

    promo, discount = validate_promo_code(
        user=user,
        code=code,
        subtotal=subtotal,
    )

    return promo, subtotal, discount

CHECKOUT_PAYMENT_WINDOW = timedelta(hours=24)


def _checkout_request_data(
    *,
    checkout_key,
    address_id,
    shipping_method_id,
    payment_method_id,
    promo_code,
):
    try:
        key = UUID(str(checkout_key))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError(
            "checkout_key harus berupa UUID yang valid."
        ) from None

    data = {
        "address_id": address_id,
        "shipping_method_id": shipping_method_id,
        "payment_method_id": payment_method_id,
    }

    for field, value in data.items():
        if type(value) is not int or not 1 <= value <= (2**63 - 1):
            raise ValidationError(f"{field} tidak valid.")

    if promo_code is not None:
        if not isinstance(promo_code, str):
            raise ValidationError("Kode promo wajib berupa teks.")

        promo_code = promo_code.strip()

        if not promo_code or len(promo_code) > 50:
            raise ValidationError("Kode promo tidak valid.")

    data["promo_code"] = promo_code

    return key, data


def _checkout_address_snapshot(address):
    fields = (
        "label",
        "recipient_name",
        "recipient_phone",
        "street_address",
        "subdistrict",
        "city",
        "province",
        "postal_code",
    )

    if any(not getattr(address, field).strip() for field in fields):
        raise ValidationError("Alamat pengiriman belum lengkap.")

    return (
        f"{address.label.strip()}\n"
        f"{address.recipient_name.strip()} | "
        f"{address.recipient_phone.strip()}\n"
        f"{address.street_address.strip()}\n"
        f"{address.subdistrict.strip()}, "
        f"{address.city.strip()}, "
        f"{address.province.strip()} "
        f"{address.postal_code.strip()}"
    )


@transaction.atomic
def checkout_cart(
    *,
    user,
    checkout_key,
    address_id,
    shipping_method_id,
    payment_method_id,
    promo_code=None,
):
    _validate_cart_user(user)

    key, request_data = _checkout_request_data(
        checkout_key=checkout_key,
        address_id=address_id,
        shipping_method_id=shipping_method_id,
        payment_method_id=payment_method_id,
        promo_code=promo_code,
    )

    locked_user = (
        get_user_model().objects
        .select_for_update()
        .filter(pk=user.pk, is_active=True)
        .first()
    )

    if locked_user is None:
        raise ValidationError("Silakan login terlebih dahulu.")

    existing = Order.objects.filter(
        user=locked_user,
        checkout_key=key,
    ).first()

    if existing is not None:
        if existing.checkout_payload != request_data:
            raise ValidationError(
                "Kunci checkout sudah digunakan untuk data yang berbeda."
            )

        return existing, False

    address = (
        UserAddress.objects
        .select_for_update()
        .filter(pk=address_id, user=locked_user)
        .first()
    )

    if address is None:
        raise ValidationError("Alamat pengiriman tidak ditemukan.")

    address_snapshot = _checkout_address_snapshot(address)

    shipping = (
        ShippingMethod.objects
        .select_for_update()
        .filter(pk=shipping_method_id, is_active=True)
        .first()
    )

    if shipping is None:
        raise ValidationError("Metode pengiriman tidak tersedia.")

    method = (
        PaymentMethod.objects
        .select_for_update()
        .filter(pk=payment_method_id, is_active=True)
        .first()
    )

    if method is None:
        raise ValidationError("Metode pembayaran tidak tersedia.")

    initial_items = dict(
        Cart.objects.filter(user=locked_user)
        .values_list("pk", "product_variant_id")
    )

    if not initial_items:
        raise ValidationError("Keranjang masih kosong.")

    variant_ids = set(initial_items.values())

    variants = {
        variant.pk: variant
        for variant in (
            ProductVariant.objects
            .select_for_update()
            .filter(pk__in=variant_ids)
            .order_by("pk")
        )
    }

    if len(variants) != len(variant_ids):
        raise ValidationError("Produk dalam keranjang tidak tersedia.")

    product_ids = {variant.product_id for variant in variants.values()}

    products = {
        product.pk: product
        for product in (
            Product.objects
            .select_for_update()
            .filter(pk__in=product_ids)
            .order_by("pk")
        )
    }

    if len(products) != len(product_ids):
        raise ValidationError("Produk dalam keranjang tidak tersedia.")

    items = list(
        Cart.objects
        .select_for_update()
        .filter(user=locked_user)
        .order_by("pk")
    )

    current_items = {
        item.pk: item.product_variant_id
        for item in items
    }

    if current_items != initial_items:
        raise ValidationError(
            "Keranjang berubah. Silakan ulangi checkout."
        )

    subtotal = Decimal("0.00")

    for item in items:
        _validate_cart_quantity(item.quantity)

        variant = variants[item.product_variant_id]
        product = products[variant.product_id]

        if item.quantity > variant.stock:
            raise ValidationError(
                f"Stok {product.name} ({variant.color_name}) "
                "tidak mencukupi."
            )

        if not product.price.is_finite() or product.price < 0:
            raise ValidationError("Harga produk tidak valid.")

        subtotal += product.price * item.quantity

    if subtotal <= 0 or subtotal > MAX_SUBTOTAL:
        raise ValidationError("Subtotal pesanan tidak valid.")

    promo = None
    discount = Decimal("0.00")
    normalized_code = request_data["promo_code"]

    if normalized_code is not None:
        locked_promo = (
            PromoCode.objects
            .select_for_update()
            .filter(code=normalized_code)
            .first()
        )

        if locked_promo is None:
            raise ValidationError("Kode promo tidak ditemukan.")

        promo, discount = validate_promo_code(
            user=locked_user,
            code=normalized_code,
            subtotal=subtotal,
        )

    if shipping.base_cost < 0 or method.service_fee < 0:
        raise ValidationError(
            "Biaya pengiriman atau layanan tidak valid."
        )

    total = (
        subtotal
        + shipping.base_cost
        + method.service_fee
        - discount
    )

    if total < 0 or total > MAX_SUBTOTAL:
        raise ValidationError("Total pesanan tidak valid.")

    needs_payment = total > 0

    order = Order.objects.create(
        order_number=f"ORD-{uuid4().hex.upper()}",
        user=locked_user,
        shipping_method=shipping,
        promo_code=promo,
        shipping_address_snapshot=address_snapshot,
        subtotal=subtotal,
        shipping_fee=shipping.base_cost,
        service_fee=method.service_fee,
        discount_amount=discount,
        total_amount=total,
        status=(
            Order.Status.TO_PAY
            if needs_payment
            else Order.Status.PROCESSING
        ),
        payment_due_at=(
            timezone.now() + CHECKOUT_PAYMENT_WINDOW
            if needs_payment
            else None
        ),
        checkout_key=key,
        checkout_payload=request_data,
        stock_deducted=True,
    )

    purchased_items = []

    for item in items:
        variant = variants[item.product_variant_id]
        product = products[variant.product_id]

        changed = ProductVariant.objects.filter(
            pk=variant.pk,
            stock__gte=item.quantity,
        ).update(stock=F("stock") - item.quantity)

        if changed == 0:
            raise ValidationError(
                "Stok berubah. Silakan ulangi checkout."
            )

        purchased_items.append(
            OrderItem(
                order=order,
                product_variant=variant,
                product_name_snapshot=product.name,
                variant_name_snapshot=variant.color_name,
                sku_snapshot=variant.sku,
                quantity=item.quantity,
                price_at_purchase=product.price,
            )
        )

    OrderItem.objects.bulk_create(purchased_items)

    if needs_payment:
        create_payment_transaction(
            user=locked_user,
            order_id=order.pk,
            payment_method_id=method.pk,
        )
    else:
        # Seluruh tagihan sudah ditutup oleh diskon.
        Payment.objects.create(
            order=order,
            payment_method=method,
            payment_reference=f"FREE-{uuid4().hex.upper()}",
            payment_amount=total,
            payment_status=Payment.Status.SUCCESS,
            paid_at=timezone.now(),
        )

    OrderTracking.objects.create(
        order=order,
        status_code=OrderTracking.StatusCode.ORDER_PLACED,
        description="Pesanan berhasil dibuat.",
        event_time=timezone.now(),
        is_completed=True,
    )

    if not needs_payment:
        OrderTracking.objects.create(
            order=order,
            status_code=OrderTracking.StatusCode.PAYMENT_CONFIRMED,
            description="Pesanan lunas tanpa tagihan pembayaran.",
            event_time=timezone.now(),
            is_completed=True,
        )

    Cart.objects.filter(
        user=locked_user,
        pk__in=[item.pk for item in items],
    ).delete()

    return order, True

MAX_PRODUCT_STOCK = 2_147_483_647


def _restore_order_stock(order):
    """
    Dipanggil dalam transaksi setelah Order dikunci.
    Perubahan stock_deducted disimpan oleh fungsi pemanggil.
    """
    if not order.stock_deducted:
        return

    items = list(
        order.items
        .order_by("pk")
        .values_list("product_variant_id", "quantity")
    )

    if not items:
        raise ValidationError(
            "Data item pesanan tidak lengkap. Stok belum bisa dikembalikan."
        )

    quantities = {}

    for variant_id, quantity in items:
        if not 1 <= quantity <= MAX_PRODUCT_STOCK:
            raise ValidationError("Jumlah item pesanan tidak valid.")

        # Varian yang sudah dihapus tetap memiliki riwayat OrderItem.
        if variant_id is None:
            continue

        quantities[variant_id] = quantities.get(variant_id, 0) + quantity

        if quantities[variant_id] > MAX_PRODUCT_STOCK:
            raise ValidationError(
                "Jumlah stok yang dikembalikan melebihi batas penyimpanan."
            )

    variants = list(
        ProductVariant.objects
        .select_for_update()
        .filter(pk__in=sorted(quantities))
        .order_by("pk")
    )

    for variant in variants:
        quantity = quantities[variant.pk]

        changed = (
            ProductVariant.objects
            .filter(
                pk=variant.pk,
                stock__lte=MAX_PRODUCT_STOCK - quantity,
            )
            .update(stock=F("stock") + quantity)
        )

        if changed != 1:
            raise ValidationError(
                "Stok tidak dapat dikembalikan karena melebihi batas penyimpanan."
            )

    order.stock_deducted = False


@transaction.atomic
def cancel_order(*, user, order_id):
    _validate_cart_user(user)

    if type(order_id) is not int or not 1 <= order_id <= (2**63 - 1):
        raise ValidationError("ID pesanan tidak valid.")

    order = (
        Order.objects
        .select_for_update()
        .filter(pk=order_id, user=user)
        .first()
    )

    if order is None:
        raise ValidationError("Pesanan tidak ditemukan.")

    # Pengulangan pembatalan tidak mengubah stok atau tracking lagi.
    if order.status == Order.Status.CANCELLED:
        return order

    if order.status != Order.Status.TO_PAY:
        raise ValidationError(
            "Hanya pesanan berstatus to_pay yang bisa dibatalkan."
        )

    payment_statuses = list(
        Payment.objects
        .select_for_update()
        .filter(order=order)
        .order_by("pk")
        .values_list("payment_status", flat=True)
    )

    if Payment.Status.SUCCESS in payment_statuses:
        raise ValidationError(
            "Pesanan sudah memiliki pembayaran berhasil dan tidak bisa dibatalkan."
        )

    _restore_order_stock(order)

    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status", "stock_deducted"])

    Payment.objects.filter(
        order=order,
        payment_status=Payment.Status.PENDING,
    ).update(
        payment_status=Payment.Status.CANCELLED,
    )

    OrderTracking.objects.create(
        order=order,
        status_code=OrderTracking.StatusCode.CANCELLED,
        description="Pesanan dibatalkan oleh pembeli.",
        event_time=timezone.now(),
        is_completed=True,
    )

    return order

@transaction.atomic
def expire_unpaid_order(*, order_id):
    if type(order_id) is not int or not 1 <= order_id <= (2**63 - 1):
        raise ValidationError("ID pesanan tidak valid.")

    order = (
        Order.objects
        .select_for_update()
        .filter(pk=order_id)
        .first()
    )

    if order is None or order.status != Order.Status.TO_PAY:
        return False

    now = timezone.now()

    if order.payment_due_at is None or order.payment_due_at > now:
        return False

    payment_statuses = list(
        Payment.objects
        .select_for_update()
        .filter(order=order)
        .order_by("pk")
        .values_list("payment_status", flat=True)
    )

    if Payment.Status.SUCCESS in payment_statuses:
        return False

    _restore_order_stock(order)

    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status", "stock_deducted"])

    Payment.objects.filter(
        order=order,
        payment_status=Payment.Status.PENDING,
    ).update(
        payment_status=Payment.Status.EXPIRED,
    )

    OrderTracking.objects.create(
        order=order,
        status_code=OrderTracking.StatusCode.CANCELLED,
        description=(
            "Pesanan dibatalkan otomatis karena "
            "batas waktu pembayaran telah habis."
        ),
        event_time=now,
        is_completed=True,
    )

    return True