from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from .models import (
    DiscountType,
    Order,
    PromoCode,
    ShippingMethod,
)
from .models import OrderTracking
from .models import Payment, PaymentMethod
from .services import validate_promo_code


class PromoCodeServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="promo-test@example.com",
            full_name="Pembeli Uji",
        )

        self.shipping = ShippingMethod.objects.create(
            name="Reguler",
            estimated_days="2-4 hari",
            base_cost="15000.00",
        )

        self.promo = PromoCode.objects.create(
            code="HEMAT10",
            discount_type=DiscountType.PERCENTAGE,
            discount_value="10.00",
            max_discount="20000.00",
            min_order_amount="100000.00",
            quota_total=100,
            quota_per_user=1,
            expires_at=timezone.now() + timedelta(days=7),
        )

    def _validate(self, subtotal="300000.00"):
        return validate_promo_code(
            user=self.user,
            code=self.promo.code,
            subtotal=Decimal(subtotal),
        )

    def _create_order(self, **changes):
        data = {
            "order_number": uuid4().hex,
            "user": self.user,
            "shipping_method": self.shipping,
            "promo_code": self.promo,
            "shipping_address_snapshot": "Alamat pengujian",
            "subtotal": "150000.00",
            "shipping_fee": "15000.00",
            "discount_amount": "15000.00",
            "total_amount": "150000.00",
            "payment_due_at": (
                timezone.now() + timedelta(days=1)
            ),
        }
        data.update(changes)
        return Order.objects.create(**data)

    def test_percentage_discount_respects_maximum(self):
        _, discount = self._validate()

        # 10% dari 300.000 = 30.000, dibatasi menjadi 20.000.
        self.assertEqual(discount, Decimal("20000.00"))

    def test_expired_promo_is_rejected(self):
        self.promo.expires_at = (
            timezone.now() - timedelta(seconds=1)
        )
        self.promo.save()

        with self.assertRaisesMessage(
            ValidationError, "sudah kedaluwarsa"
        ):
            self._validate()

    def test_inactive_promo_is_rejected(self):
        self.promo.is_active = False
        self.promo.save()

        with self.assertRaisesMessage(
            ValidationError, "tidak aktif"
        ):
            self._validate()

    def test_minimum_purchase_is_checked(self):
        with self.assertRaisesMessage(
            ValidationError, "minimum belanja"
        ):
            self._validate("99999.99")

    def test_user_quota_is_checked(self):
        self._create_order()

        with self.assertRaisesMessage(
            ValidationError, "untuk akun ini"
        ):
            self._validate()

    def test_total_quota_is_checked(self):
        other_user = get_user_model().objects.create_user(
            email="pembeli-lain@example.com",
            full_name="Pembeli Lain",
        )

        self.promo.quota_total = 1
        self.promo.save()

        self._create_order(user=other_user)

        with self.assertRaisesMessage(
            ValidationError, "Kuota promo sudah habis"
        ):
            self._validate()

    def test_cancelled_and_expired_orders_release_quota(self):
        self._create_order(
            status=Order.Status.CANCELLED,
        )
        self._create_order(
            payment_due_at=(
                timezone.now() - timedelta(seconds=1)
            ),
        )

        _, discount = self._validate("150000.00")

        self.assertEqual(discount, Decimal("15000.00"))

    def test_fixed_discount_cannot_exceed_subtotal(self):
        self.promo.discount_type = DiscountType.FIXED
        self.promo.discount_value = Decimal("500000.00")
        self.promo.max_discount = None
        self.promo.save()

        _, discount = self._validate("150000.00")

        self.assertEqual(discount, Decimal("150000.00"))

class OrderTrackingViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="tracking@example.com",
            full_name="Pemilik Pesanan",
        )
        self.other_user = get_user_model().objects.create_user(
            email="other@example.com",
            full_name="Pengguna Lain",
        )

        shipping = ShippingMethod.objects.create(
            name="Reguler",
            estimated_days="2-4 hari",
            base_cost="15000.00",
        )

        self.order = Order.objects.create(
            order_number="TRACK-TEST-001",
            user=self.user,
            shipping_method=shipping,
            shipping_address_snapshot="Alamat pengujian",
            subtotal="100000.00",
            shipping_fee="15000.00",
            total_amount="115000.00",
        )

        OrderTracking.objects.create(
            order=self.order,
            status_code=OrderTracking.StatusCode.ORDER_PLACED,
            description="Pesanan berhasil dibuat.",
            event_time=timezone.now(),
            is_completed=True,
        )

        self.url = (
            f"/api/orders/{self.order.pk}/tracking/"
        )

    def test_login_is_required(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 401)

    def test_owner_can_view_tracking(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

        data = response.json()["data"]

        self.assertEqual(data["order_id"], self.order.pk)
        self.assertEqual(len(data["tracking"]), 1)
        self.assertEqual(
            data["tracking"][0]["status_code"],
            OrderTracking.StatusCode.ORDER_PLACED,
        )

    def test_other_user_cannot_view_tracking(self):
        self.client.force_login(self.other_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

class OrderHistoryViewTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            email="history@example.com",
            full_name="Pemilik Pesanan",
        )

        self.other_user = User.objects.create_user(
            email="history-other@example.com",
            full_name="Pengguna Lain",
        )

        self.shipping = ShippingMethod.objects.create(
            name="Reguler",
            estimated_days="2-4 hari",
            base_cost="15000.00",
        )

        self.method = PaymentMethod.objects.create(
            name="Transfer Bank",
            channel_provider="Manual",
            service_fee="2500.00",
        )

        self.order = self._create_order(
            self.user,
            "HISTORY-001",
        )

        self._create_order(
            self.other_user,
            "HISTORY-002",
        )

        self.payment = Payment.objects.create(
            order=self.order,
            payment_method=self.method,
            payment_reference="PAY-TEST-PENDING",
            payment_amount="117500.00",
        )

        self.url = "/api/orders/"

    def _create_order(self, user, number):
        return Order.objects.create(
            order_number=number,
            user=user,
            shipping_method=self.shipping,
            shipping_address_snapshot="Alamat pengujian",
            subtotal="100000.00",
            shipping_fee="15000.00",
            service_fee="2500.00",
            total_amount="117500.00",
        )

    def test_login_is_required(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 401)

    def test_only_own_orders_are_returned(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

        payload = response.json()
        order_ids = [
            order["id"] for order in payload["data"]
        ]

        self.assertEqual(order_ids, [self.order.pk])
        self.assertEqual(payload["meta"]["total"], 1)

    def test_payment_details_are_returned(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

        payment = response.json()["data"][0]["payment"]

        self.assertEqual(
            payment["payment_status"],
            Payment.Status.PENDING,
        )
        self.assertEqual(
            payment["payment_amount"],
            "117500.00",
        )
        self.assertEqual(
            payment["payment_reference"],
            self.payment.payment_reference,
        )

    def test_success_is_prioritized_over_latest_failure(self):
        Payment.objects.create(
            order=self.order,
            payment_method=self.method,
            payment_reference="PAY-TEST-SUCCESS",
            payment_amount="117500.00",
            payment_status=Payment.Status.SUCCESS,
            paid_at=timezone.now(),
        )

        Payment.objects.create(
            order=self.order,
            payment_method=self.method,
            payment_reference="PAY-TEST-FAILED",
            payment_amount="117500.00",
            payment_status=Payment.Status.FAILED,
        )

        self.order.status = Order.Status.PROCESSING
        self.order.save(update_fields=["status"])

        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

        payment = response.json()["data"][0]["payment"]

        self.assertEqual(
            payment["payment_status"],
            Payment.Status.SUCCESS,
        )
        self.assertEqual(
            payment["payment_reference"],
            "PAY-TEST-SUCCESS",
        )