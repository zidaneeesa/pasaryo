from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.core.paginator import Paginator
from django.db.models import Prefetch

from .models import Order, Payment, PaymentMethod, ShippingMethod


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