import json
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import (
    require_GET,
    require_POST,
    require_http_methods,
)

from .models import Cart, Order, Payment, PaymentMethod, ShippingMethod
from .services import (
    add_cart_item,
    confirm_order_received,
    create_payment_transaction,
    get_cart_items,
    remove_cart_item,
    set_cart_item_quantity,
    validate_cart_promo_code,
    checkout_cart,
    cancel_order,
)

@require_GET
def shipping_method_list(request):
    methods = ShippingMethod.objects.filter(
        is_active=True
    ).order_by("id")

    data = [
        {
            "id": method.id,
            "name": method.name,
            "estimated_days": method.estimated_days,
            "base_cost": str(method.base_cost),
        }
        for method in methods
    ]

    return JsonResponse({"data": data})


@require_GET
def payment_method_list(request):
    methods = PaymentMethod.objects.filter(
        is_active=True
    ).order_by("id")

    data = [
        {
            "id": method.id,
            "name": method.name,
            "channel_provider": method.channel_provider,
            "service_fee": str(method.service_fee),
        }
        for method in methods
    ]

    return JsonResponse({"data": data})
@require_GET
def order_tracking(request, order_id):
    if (
        not request.user.is_authenticated
        or not request.user.is_active
    ):
        return JsonResponse(
            {"message": "Silakan login terlebih dahulu."},
            status=401,
        )

    order = Order.objects.filter(
        pk=order_id,
        user=request.user,
    ).first()

    if order is None:
        return JsonResponse(
            {"message": "Pesanan tidak ditemukan."},
            status=404,
        )

    tracking = [
        {
            "id": event.id,
            "status_code": event.status_code,
            "description": event.description,
            "event_time": (
                event.event_time.isoformat()
                if event.event_time else None
            ),
            "expected_time": (
                event.expected_time.isoformat()
                if event.expected_time else None
            ),
            "is_completed": event.is_completed,
        }
        for event in order.trackings.order_by(
            "event_time", "id"
        )
    ]

    return JsonResponse({
        "data": {
            "order_id": order.id,
            "order_number": order.order_number,
            "order_status": order.status,
            "tracking": tracking,
        }
    })

@require_GET
def order_history(request):
    if (
        not request.user.is_authenticated
        or not request.user.is_active
    ):
        return JsonResponse(
            {"message": "Silakan login terlebih dahulu."},
            status=401,
        )

    orders = (
        Order.objects.filter(user=request.user)
        .select_related("shipping_method")
        .prefetch_related(
            Prefetch(
                "payments",
                queryset=Payment.objects.select_related(
                    "payment_method"
                ).order_by("-id"),
                to_attr="payment_history",
            )
        )
        .order_by("-created_at", "-id")
    )

    paginator = Paginator(orders, 20)
    page = paginator.get_page(request.GET.get("page"))

    data = []

    for order in page:
        # Utamakan pembayaran sukses.
        # Jika belum ada, gunakan percobaan terbaru.
        payment = next(
            (
                attempt
                for attempt in order.payment_history
                if attempt.payment_status == Payment.Status.SUCCESS
            ),
            (
                order.payment_history[0]
                if order.payment_history else None
            ),
        )

        payment_data = None

        if payment is not None:
            payment_data = {
                "id": payment.id,
                "payment_reference": payment.payment_reference,
                "payment_status": payment.payment_status,
                "payment_amount": str(payment.payment_amount),
                "payment_method": payment.payment_method.name,
                "expires_at": payment.expires_at,
                "paid_at": payment.paid_at,
            }

        data.append({
            "id": order.id,
            "order_number": order.order_number,
            "status": order.status,
            "created_at": order.created_at,
            "payment_due_at": order.payment_due_at,
            "shipping_method": order.shipping_method.name,
            "subtotal": str(order.subtotal),
            "shipping_fee": str(order.shipping_fee),
            "service_fee": str(order.service_fee),
            "discount_amount": str(order.discount_amount),
            "total_amount": str(order.total_amount),
            "items": _order_items_data(order),  # Baris tambahan
            "payment": payment_data,
        })
    return JsonResponse({
        "data": data,
        "meta": {
            "page": page.number,
            "per_page": 20,
            "total": paginator.count,
            "total_pages": paginator.num_pages,
        },
    })

@require_GET
def order_detail(request, order_id):
    if not request.user.is_authenticated or not request.user.is_active:
        return JsonResponse(
            {"message": "Silakan login terlebih dahulu."},
            status=401,
        )

    order = (
        Order.objects
        .select_related("shipping_method")
        .filter(pk=order_id, user=request.user)
        .first()
    )

    if order is None:
        return JsonResponse(
            {"message": "Pesanan tidak ditemukan."},
            status=404,
        )

    payments = list(
        order.payments
        .select_related("payment_method")
        .order_by("-id")
    )

    # Sama seperti riwayat: utamakan pembayaran sukses.
    # Jika belum ada yang sukses, tampilkan percobaan terbaru.
    payment = next(
        (
            item
            for item in payments
            if item.payment_status == Payment.Status.SUCCESS
        ),
        payments[0] if payments else None,
    )

    payment_data = None

    if payment is not None:
        payment_data = {
            "id": payment.id,
            "payment_reference": payment.payment_reference,
            "payment_status": payment.payment_status,
            "payment_amount": str(payment.payment_amount),
            "payment_method": payment.payment_method.name,
            "expires_at": payment.expires_at,
            "paid_at": payment.paid_at,
        }

    tracking = [
        {
            "id": event.id,
            "status_code": event.status_code,
            "description": event.description,
            "event_time": (
                event.event_time.isoformat()
                if event.event_time else None
            ),
            "expected_time": (
                event.expected_time.isoformat()
                if event.expected_time else None
            ),
            "is_completed": event.is_completed,
        }
        for event in order.trackings.order_by("event_time", "id")
    ]

    return JsonResponse({
        "data": {
            "id": order.id,
            "order_number": order.order_number,
            "status": order.status,
            "created_at": order.created_at,
            "payment_due_at": order.payment_due_at,
            "shipping_method": order.shipping_method.name,
            "shipping_address_snapshot": order.shipping_address_snapshot,
            "estimated_delivery_from": order.estimated_delivery_from,
            "estimated_delivery_to": order.estimated_delivery_to,
            "subtotal": str(order.subtotal),
            "shipping_fee": str(order.shipping_fee),
            "service_fee": str(order.service_fee),
            "discount_amount": str(order.discount_amount),
            "total_amount": str(order.total_amount),
            "items": _order_items_data(order),  # Baris tambahan
            "payment": payment_data,
            "tracking": tracking,
        }
    })

@require_POST
@csrf_protect
def payment_create(request, order_id):
    if not request.user.is_authenticated or not request.user.is_active:
        return JsonResponse(
            {"message": "Silakan login terlebih dahulu."},
            status=401,
        )

    if request.content_type != "application/json":
        return JsonResponse(
            {"message": "Gunakan Content-Type application/json."},
            status=415,
        )

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, RecursionError):
        return JsonResponse(
            {"message": "Body JSON tidak valid."},
            status=400,
        )

    if (
        not isinstance(payload, dict)
        or set(payload) != {"payment_method_id"}
    ):
        return JsonResponse(
            {"message": "Kirim hanya field payment_method_id."},
            status=400,
        )

    payment_method_id = payload["payment_method_id"]

    # Pemeriksaan tipe ini juga menolak nilai boolean.
    if (
        type(payment_method_id) is not int
        or not 1 <= payment_method_id <= (2**63 - 1)
    ):
        return JsonResponse(
            {
                "message": (
                    "payment_method_id harus berupa "
                    "bilangan bulat positif yang valid."
                )
            },
            status=400,
        )

    if not Order.objects.filter(
        pk=order_id,
        user=request.user,
    ).exists():
        return JsonResponse(
            {"message": "Pesanan tidak ditemukan."},
            status=404,
        )

    try:
        payment = create_payment_transaction(
            user=request.user,
            order_id=order_id,
            payment_method_id=payment_method_id,
        )
    except ValidationError as exc:
        return JsonResponse(
            {"message": " ".join(exc.messages)},
            status=400,
        )

    return JsonResponse(
        {
            "data": {
                "id": payment.id,
                "order_id": payment.order_id,
                "payment_reference": payment.payment_reference,
                "payment_status": payment.payment_status,
                "payment_amount": str(payment.payment_amount),
                "payment_method_id": payment.payment_method_id,
                "payment_method": payment.payment_method.name,
                "expires_at": payment.expires_at,
                "paid_at": payment.paid_at,
            }
        },
        status=201,
    )

def _cart_response(user, *, status=200):
    items = []
    subtotal = Decimal("0.00")

    for item in get_cart_items(user=user):
        variant = item.product_variant
        product = variant.product
        line_total = product.price * item.quantity

        subtotal += line_total

        items.append({
            "id": item.pk,
            "product_id": product.pk,
            "product_variant_id": variant.pk,
            "product_name": product.name,
            "color_name": variant.color_name,
            "sku": variant.sku,
            "quantity": item.quantity,
            "stock": variant.stock,
            "unit_price": str(product.price),
            "line_total": str(line_total),
            "is_available": item.quantity <= variant.stock,
        })

    return JsonResponse(
        {
            "data": {
                "items": items,
                "subtotal": str(subtotal),
                "total_quantity": sum(
                    item["quantity"] for item in items
                ),
                "has_stock_issue": any(
                    not item["is_available"] for item in items
                ),
            }
        },
        status=status,
    )


def _read_cart_payload(request, *, expected_fields):
    if request.content_type != "application/json":
        return None, JsonResponse(
            {"message": "Gunakan Content-Type application/json."},
            status=415,
        )

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, RecursionError):
        return None, JsonResponse(
            {"message": "Body JSON tidak valid."},
            status=400,
        )

    if (
        not isinstance(payload, dict)
        or set(payload) != expected_fields
    ):
        fields = ", ".join(sorted(expected_fields))

        return None, JsonResponse(
            {"message": f"Kirim hanya field berikut: {fields}."},
            status=400,
        )

    return payload, None


@require_http_methods(["GET", "POST"])
@csrf_protect
def cart_collection(request):
    if not request.user.is_authenticated or not request.user.is_active:
        return JsonResponse(
            {"message": "Silakan login terlebih dahulu."},
            status=401,
        )

    if request.method == "GET":
        return _cart_response(request.user)

    payload, error = _read_cart_payload(
        request,
        expected_fields={"product_variant_id", "quantity"},
    )

    if error is not None:
        return error

    variant_id = payload["product_variant_id"]

    if (
        type(variant_id) is not int
        or not 1 <= variant_id <= (2**63 - 1)
    ):
        return JsonResponse(
            {"message": "product_variant_id tidak valid."},
            status=400,
        )

    try:
        _, created = add_cart_item(
            user=request.user,
            product_variant_id=variant_id,
            quantity=payload["quantity"],
        )
    except ValidationError as exc:
        return JsonResponse(
            {"message": " ".join(exc.messages)},
            status=400,
        )

    return _cart_response(
        request.user,
        status=201 if created else 200,
    )


@require_http_methods(["PATCH", "DELETE"])
@csrf_protect
def cart_item_detail(request, cart_item_id):
    if not request.user.is_authenticated or not request.user.is_active:
        return JsonResponse(
            {"message": "Silakan login terlebih dahulu."},
            status=401,
        )

    if not Cart.objects.filter(
        pk=cart_item_id,
        user=request.user,
    ).exists():
        return JsonResponse(
            {"message": "Item keranjang tidak ditemukan."},
            status=404,
        )

    if request.method == "PATCH":
        payload, error = _read_cart_payload(
            request,
            expected_fields={"quantity"},
        )

        if error is not None:
            return error

    try:
        if request.method == "PATCH":
            set_cart_item_quantity(
                user=request.user,
                cart_item_id=cart_item_id,
                quantity=payload["quantity"],
            )
        else:
            remove_cart_item(
                user=request.user,
                cart_item_id=cart_item_id,
            )
    except ValidationError as exc:
        return JsonResponse(
            {"message": " ".join(exc.messages)},
            status=400,
        )

    return _cart_response(request.user)

@require_POST
@csrf_protect
def promo_code_validate(request):
    if not request.user.is_authenticated or not request.user.is_active:
        return JsonResponse(
            {"message": "Silakan login terlebih dahulu."},
            status=401,
        )

    payload, error = _read_cart_payload(
        request,
        expected_fields={"code"},
    )

    if error is not None:
        return error

    try:
        promo, subtotal, discount = validate_cart_promo_code(
            user=request.user,
            code=payload["code"],
        )
    except ValidationError as exc:
        return JsonResponse(
            {"message": " ".join(exc.messages)},
            status=400,
        )

    return JsonResponse({
        "data": {
            "code": promo.code,
            "subtotal": str(subtotal),
            "discount_amount": str(discount),
            "subtotal_after_discount": str(subtotal - discount),
        }
    })

@require_POST
@csrf_protect
def order_complete(request, order_id):
    if not request.user.is_authenticated or not request.user.is_active:
        return JsonResponse(
            {"message": "Silakan login terlebih dahulu."},
            status=401,
        )

    if not Order.objects.filter(
        pk=order_id,
        user=request.user,
    ).exists():
        return JsonResponse(
            {"message": "Pesanan tidak ditemukan."},
            status=404,
        )

    try:
        order = confirm_order_received(
            user=request.user,
            order_id=order_id,
        )
    except ValidationError as exc:
        return JsonResponse(
            {"message": " ".join(exc.messages)},
            status=400,
        )

    return JsonResponse({
        "message": "Pesanan berhasil dikonfirmasi diterima.",
        "data": {
            "id": order.pk,
            "order_number": order.order_number,
            "status": order.status,
        },
    })

def _order_items_data(order):
    return [
        {
            "id": item.pk,
            "product_variant_id": item.product_variant_id,
            "product_name": item.product_name_snapshot,
            "variant_name": item.variant_name_snapshot,
            "sku": item.sku_snapshot,
            "quantity": item.quantity,
            "unit_price": str(item.price_at_purchase),
            "line_total": str(item.line_total),
        }
        for item in order.items.all()
    ]

@require_POST
@csrf_protect
def checkout_create(request):
    if not request.user.is_authenticated or not request.user.is_active:
        return JsonResponse(
            {"message": "Silakan login terlebih dahulu."},
            status=401,
        )

    if request.content_type != "application/json":
        return JsonResponse(
            {"message": "Gunakan Content-Type application/json."},
            status=415,
        )

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, RecursionError):
        return JsonResponse(
            {"message": "Body JSON tidak valid."},
            status=400,
        )

    required_fields = {
        "checkout_key",
        "address_id",
        "shipping_method_id",
        "payment_method_id",
    }
    allowed_fields = required_fields | {"promo_code"}

    if (
        not isinstance(payload, dict)
        or not required_fields.issubset(payload)
        or not set(payload).issubset(allowed_fields)
    ):
        return JsonResponse(
            {
                "message": (
                    "Kirim checkout_key, address_id, shipping_method_id, "
                    "dan payment_method_id. Field promo_code bersifat opsional."
                )
            },
            status=400,
        )

    try:
        order, created = checkout_cart(
            user=request.user,
            checkout_key=payload["checkout_key"],
            address_id=payload["address_id"],
            shipping_method_id=payload["shipping_method_id"],
            payment_method_id=payload["payment_method_id"],
            promo_code=payload.get("promo_code"),
        )
    except ValidationError as exc:
        return JsonResponse(
            {"message": " ".join(exc.messages)},
            status=400,
        )

    payments = (
        order.payments
        .select_related("payment_method")
        .order_by("-id")
    )

    payment = (
        payments.filter(payment_status=Payment.Status.SUCCESS).first()
        or payments.first()
    )

    payment_data = None

    if payment is not None:
        payment_data = {
            "id": payment.pk,
            "payment_reference": payment.payment_reference,
            "payment_status": payment.payment_status,
            "payment_amount": str(payment.payment_amount),
            "payment_method_id": payment.payment_method_id,
            "payment_method": payment.payment_method.name,
            "payment_url": payment.payment_url,
            "expires_at": (
                payment.expires_at.isoformat()
                if payment.expires_at
                else None
            ),
            "paid_at": (
                payment.paid_at.isoformat()
                if payment.paid_at
                else None
            ),
        }

    return JsonResponse(
        {
            "data": {
                "id": order.pk,
                "checkout_key": str(order.checkout_key),
                "order_number": order.order_number,
                "status": order.status,
                "shipping_method": order.shipping_method.name,
                "shipping_address_snapshot": order.shipping_address_snapshot,
                "subtotal": str(order.subtotal),
                "shipping_fee": str(order.shipping_fee),
                "service_fee": str(order.service_fee),
                "discount_amount": str(order.discount_amount),
                "total_amount": str(order.total_amount),
                "payment_due_at": (
                    order.payment_due_at.isoformat()
                    if order.payment_due_at
                    else None
                ),
                "items": _order_items_data(order),
                "payment": payment_data,
            }
        },
        status=201 if created else 200,
    )

@require_POST
@csrf_protect
def order_cancel(request, order_id):
    if not request.user.is_authenticated or not request.user.is_active:
        return JsonResponse(
            {"message": "Silakan login terlebih dahulu."},
            status=401,
        )

    if not (
        1 <= order_id <= (2**63 - 1)
        and Order.objects.filter(
            pk=order_id,
            user=request.user,
        ).exists()
    ):
        return JsonResponse(
            {"message": "Pesanan tidak ditemukan."},
            status=404,
        )

    try:
        order = cancel_order(
            user=request.user,
            order_id=order_id,
        )
    except ValidationError as exc:
        return JsonResponse(
            {"message": " ".join(exc.messages)},
            status=400,
        )

    return JsonResponse(
        {
            "message": "Pesanan berhasil dibatalkan.",
            "data": {
                "id": order.pk,
                "order_number": order.order_number,
                "status": order.status,
            },
        },
        status=200,
    )