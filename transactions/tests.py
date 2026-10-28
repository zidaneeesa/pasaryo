from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.utils import timezone
from django.contrib.auth.models import AnonymousUser
from django.conf import settings
from django.db import IntegrityError, transaction
from django.core.management import call_command
from django.core.management.base import CommandError

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
from .services import (
    add_cart_item,
    checkout_cart,
    confirm_order_received,
    create_payment_transaction,
    get_cart_items,
    remove_cart_item,
    set_cart_item_quantity,
    validate_cart_promo_code,
    validate_promo_code,
    cancel_order,
    expire_unpaid_order,
)

from accounts.models import UserAddress
from catalog.models import Brand, Category, Product, ProductVariant
from unittest.mock import patch


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

class OrderDetailViewTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            email="detail@example.com",
            full_name="Pemilik Pesanan",
        )

        self.other_user = User.objects.create_user(
            email="detail-other@example.com",
            full_name="Pengguna Lain",
        )

        self.shipping = ShippingMethod.objects.create(
            name="Reguler",
            estimated_days="2-4 hari",
            base_cost=Decimal("15000.00"),
        )

        self.method = PaymentMethod.objects.create(
            name="Transfer Bank",
            channel_provider="Manual",
            service_fee=Decimal("2500.00"),
        )

        self.order = Order.objects.create(
            order_number="DETAIL-001",
            user=self.user,
            shipping_method=self.shipping,
            shipping_address_snapshot="Penerima Uji, Jalan Contoh, Jember",
            subtotal=Decimal("100000.00"),
            shipping_fee=Decimal("15000.00"),
            service_fee=Decimal("2500.00"),
            discount_amount=Decimal("10000.00"),
            total_amount=Decimal("107500.00"),
        )

        self.payment = Payment.objects.create(
            order=self.order,
            payment_method=self.method,
            payment_reference="DETAIL-PAY-PENDING",
            payment_amount=self.order.total_amount,
        )

        OrderTracking.objects.create(
            order=self.order,
            status_code=OrderTracking.StatusCode.ORDER_PLACED,
            description="Pesanan berhasil dibuat.",
            event_time=timezone.now(),
            is_completed=True,
        )

        self.url = f"/api/orders/{self.order.pk}/"

    def test_login_is_required(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 401)

    def test_owner_can_view_detail(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

        data = response.json()["data"]

        self.assertEqual(data["id"], self.order.pk)
        self.assertEqual(data["order_number"], "DETAIL-001")
        self.assertEqual(
            data["shipping_address_snapshot"],
            "Penerima Uji, Jalan Contoh, Jember",
        )

        self.assertEqual(data["subtotal"], "100000.00")
        self.assertEqual(data["shipping_fee"], "15000.00")
        self.assertEqual(data["service_fee"], "2500.00")
        self.assertEqual(data["discount_amount"], "10000.00")
        self.assertEqual(data["total_amount"], "107500.00")

        self.assertEqual(
            data["payment"]["payment_reference"],
            "DETAIL-PAY-PENDING",
        )
        self.assertEqual(
            data["payment"]["payment_status"],
            Payment.Status.PENDING,
        )

        self.assertEqual(len(data["tracking"]), 1)
        self.assertEqual(
            data["tracking"][0]["status_code"],
            OrderTracking.StatusCode.ORDER_PLACED,
        )

    def test_other_user_cannot_view_detail(self):
        self.client.force_login(self.other_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {"message": "Pesanan tidak ditemukan."},
        )

    def test_missing_order_returns_404(self):
        self.order.delete()
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_no_payment_is_returned_as_null(self):
        self.payment.delete()
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["data"]["payment"])

    def test_success_payment_is_prioritized(self):
        Payment.objects.create(
            order=self.order,
            payment_method=self.method,
            payment_reference="DETAIL-PAY-SUCCESS",
            payment_amount=self.order.total_amount,
            payment_status=Payment.Status.SUCCESS,
            paid_at=timezone.now(),
        )

        # Percobaan gagal ini dibuat setelah pembayaran sukses.
        Payment.objects.create(
            order=self.order,
            payment_method=self.method,
            payment_reference="DETAIL-PAY-FAILED",
            payment_amount=self.order.total_amount,
            payment_status=Payment.Status.FAILED,
        )

        self.order.status = Order.Status.PROCESSING
        self.order.save(update_fields=["status"])

        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

        payment = response.json()["data"]["payment"]

        self.assertEqual(
            payment["payment_reference"],
            "DETAIL-PAY-SUCCESS",
        )
        self.assertEqual(
            payment["payment_status"],
            Payment.Status.SUCCESS,
        )

class PaymentTransactionServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            email="payment@example.com",
            full_name="Pembeli Pembayaran",
        )

        self.other_user = User.objects.create_user(
            email="payment-other@example.com",
            full_name="Pengguna Lain",
        )

        self.shipping = ShippingMethod.objects.create(
            name="Reguler",
            estimated_days="2-4 hari",
            base_cost=Decimal("15000.00"),
        )

        self.method = PaymentMethod.objects.create(
            name="Transfer Bank",
            channel_provider="Manual",
            service_fee=Decimal("2500.00"),
        )

        self.order = Order.objects.create(
            order_number="PAYMENT-ORDER-001",
            user=self.user,
            shipping_method=self.shipping,
            shipping_address_snapshot="Alamat pengujian, Jember",
            subtotal=Decimal("100000.00"),
            shipping_fee=Decimal("15000.00"),
            service_fee=Decimal("2500.00"),
            discount_amount=Decimal("0.00"),
            total_amount=Decimal("117500.00"),
            payment_due_at=timezone.now() + timedelta(hours=24),
        )

    def _create_payment(self, **changes):
        arguments = {
            "user": self.user,
            "order_id": self.order.pk,
            "payment_method_id": self.method.pk,
        }
        arguments.update(changes)

        return create_payment_transaction(**arguments)

    def test_pending_payment_is_created(self):
        payment = self._create_payment()
        payment.refresh_from_db()

        self.assertEqual(payment.order_id, self.order.pk)
        self.assertEqual(payment.payment_method_id, self.method.pk)
        self.assertEqual(
            payment.payment_amount,
            Decimal("117500.00"),
        )
        self.assertEqual(
            payment.payment_status,
            Payment.Status.PENDING,
        )
        self.assertEqual(
            payment.expires_at,
            self.order.payment_due_at,
        )
        self.assertTrue(payment.payment_reference.startswith("PAY-"))
        self.assertIsNone(payment.paid_at)

    def test_login_is_required(self):
        with self.assertRaisesMessage(ValidationError, "login"):
            self._create_payment(user=AnonymousUser())

        self.assertEqual(Payment.objects.count(), 0)

    def test_other_user_cannot_create_payment(self):
        with self.assertRaisesMessage(
            ValidationError,
            "Pesanan tidak ditemukan",
        ):
            self._create_payment(user=self.other_user)

        self.assertEqual(Payment.objects.count(), 0)

    def test_non_payable_order_is_rejected(self):
        statuses = (
            Order.Status.PROCESSING,
            Order.Status.SHIPPED,
            Order.Status.COMPLETED,
            Order.Status.CANCELLED,
        )

        for status in statuses:
            with self.subTest(status=status):
                self.order.status = status
                self.order.save(update_fields=["status"])

                with self.assertRaisesMessage(
                    ValidationError,
                    "menunggu pembayaran",
                ):
                    self._create_payment()

                self.assertEqual(Payment.objects.count(), 0)

    def test_missing_or_expired_deadline_is_rejected(self):
        deadlines = (
            None,
            timezone.now() - timedelta(seconds=1),
        )

        for deadline in deadlines:
            with self.subTest(deadline=deadline):
                self.order.payment_due_at = deadline
                self.order.save(update_fields=["payment_due_at"])

                with self.assertRaisesMessage(
                    ValidationError,
                    "Batas waktu pembayaran",
                ):
                    self._create_payment()

                self.assertEqual(Payment.objects.count(), 0)

    def test_inactive_payment_method_is_rejected(self):
        self.method.is_active = False
        self.method.save(update_fields=["is_active"])

        with self.assertRaisesMessage(
            ValidationError,
            "Metode pembayaran tidak tersedia",
        ):
            self._create_payment()

        self.assertEqual(Payment.objects.count(), 0)

    def test_service_fee_must_match_payment_method(self):
        self.method.service_fee = Decimal("3000.00")
        self.method.save(update_fields=["service_fee"])

        with self.assertRaisesMessage(
            ValidationError,
            "Biaya layanan",
        ):
            self._create_payment()

        self.assertEqual(Payment.objects.count(), 0)

    def test_inconsistent_total_is_rejected(self):
        self.order.total_amount = Decimal("1.00")
        self.order.save(update_fields=["total_amount"])

        with self.assertRaisesMessage(
            ValidationError,
            "Rincian total pesanan tidak valid",
        ):
            self._create_payment()

        self.assertEqual(Payment.objects.count(), 0)

    def test_successful_payment_prevents_new_attempt(self):
        Payment.objects.create(
            order=self.order,
            payment_method=self.method,
            payment_reference="PAY-ALREADY-SUCCESS",
            payment_amount=self.order.total_amount,
            payment_status=Payment.Status.SUCCESS,
            paid_at=timezone.now(),
        )

        with self.assertRaisesMessage(
            ValidationError,
            "pembayaran sukses",
        ):
            self._create_payment()

        self.assertEqual(Payment.objects.count(), 1)

class PaymentCreateViewTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            email="payment-view@example.com",
            full_name="Pemilik Pesanan",
        )

        self.other_user = User.objects.create_user(
            email="payment-view-other@example.com",
            full_name="Pengguna Lain",
        )

        self.shipping = ShippingMethod.objects.create(
            name="Reguler",
            estimated_days="2-4 hari",
            base_cost=Decimal("15000.00"),
        )

        self.method = PaymentMethod.objects.create(
            name="Transfer Bank",
            channel_provider="Manual",
            service_fee=Decimal("2500.00"),
        )

        self.order = Order.objects.create(
            order_number="PAYMENT-VIEW-001",
            user=self.user,
            shipping_method=self.shipping,
            shipping_address_snapshot="Alamat pengujian, Jember",
            subtotal=Decimal("100000.00"),
            shipping_fee=Decimal("15000.00"),
            service_fee=Decimal("2500.00"),
            discount_amount=Decimal("0.00"),
            total_amount=Decimal("117500.00"),
            payment_due_at=timezone.now() + timedelta(hours=24),
        )

        self.url = f"/api/orders/{self.order.pk}/payments/"

    def _post(self, *, data=None):
        if data is None:
            data = {"payment_method_id": self.method.pk}

        return self.client.post(
            self.url,
            data=data,
            content_type="application/json",
        )

    def test_owner_can_create_payment(self):
        self.client.force_login(self.user)

        response = self._post()

        self.assertEqual(response.status_code, 201)

        data = response.json()["data"]

        self.assertEqual(data["order_id"], self.order.pk)
        self.assertEqual(data["payment_method_id"], self.method.pk)
        self.assertEqual(data["payment_amount"], "117500.00")
        self.assertEqual(
            data["payment_status"],
            Payment.Status.PENDING,
        )
        self.assertTrue(data["payment_reference"].startswith("PAY-"))

        payment = Payment.objects.get()

        self.assertEqual(payment.pk, data["id"])
        self.assertEqual(payment.order_id, self.order.pk)

    def test_login_is_required(self):
        response = self._post()

        self.assertEqual(response.status_code, 401)
        self.assertEqual(Payment.objects.count(), 0)

    def test_other_user_cannot_create_payment(self):
        self.client.force_login(self.other_user)

        response = self._post()

        self.assertEqual(response.status_code, 404)
        self.assertEqual(Payment.objects.count(), 0)

    def test_invalid_payload_is_rejected(self):
        self.client.force_login(self.user)

        invalid_payloads = (
            b'{"payment_method_id":',
            b"[]",
            b"null",
            {},
            {"payment_method_id": True},
            {"payment_method_id": "1"},
            {"payment_method_id": 0},
            {"payment_method_id": -1},
            {"payment_method_id": 2**63},
            {
                "payment_method_id": self.method.pk,
                "payment_amount": "1.00",
            },
            {
                "payment_method_id": self.method.pk,
                "payment_status": "SUCCESS",
            },
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self._post(data=payload)

                self.assertEqual(response.status_code, 400)
                self.assertIn("message", response.json())
                self.assertEqual(Payment.objects.count(), 0)

    def test_non_json_is_rejected(self):
        self.client.force_login(self.user)

        response = self.client.post(
            self.url,
            data={"payment_method_id": self.method.pk},
        )

        self.assertEqual(response.status_code, 415)
        self.assertEqual(Payment.objects.count(), 0)

    def test_get_is_rejected(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)
        self.assertEqual(Payment.objects.count(), 0)

    def test_service_error_is_returned_as_json(self):
        self.method.is_active = False
        self.method.save(update_fields=["is_active"])
        self.client.force_login(self.user)

        response = self._post()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["message"],
            "Metode pembayaran tidak tersedia.",
        )
        self.assertEqual(Payment.objects.count(), 0)

    def test_csrf_is_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        payload = {"payment_method_id": self.method.pk}

        # Tanpa token CSRF, permintaan harus ditolak.
        response = client.post(
            self.url,
            data=payload,
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Payment.objects.count(), 0)

        # Token contoh ini hanya digunakan sebagai data pengujian.
        csrf_token = "a" * 32
        client.cookies[settings.CSRF_COOKIE_NAME] = csrf_token

        response = client.post(
            self.url,
            data=payload,
            content_type="application/json",
            headers={"X-CSRFToken": csrf_token},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Payment.objects.count(), 1)

class OrderCompletionServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            email="completion@example.com",
            full_name="Pemilik Pesanan",
        )

        self.other_user = User.objects.create_user(
            email="completion-other@example.com",
            full_name="Pengguna Lain",
        )

        self.shipping = ShippingMethod.objects.create(
            name="Reguler",
            estimated_days="2-4 hari",
            base_cost=Decimal("15000.00"),
        )

        self.method = PaymentMethod.objects.create(
            name="Transfer Bank",
            channel_provider="Manual",
            service_fee=Decimal("2500.00"),
        )

        self.order = Order.objects.create(
            order_number="COMPLETE-001",
            user=self.user,
            shipping_method=self.shipping,
            shipping_address_snapshot="Alamat pengujian, Jember",
            subtotal=Decimal("100000.00"),
            shipping_fee=Decimal("15000.00"),
            service_fee=Decimal("2500.00"),
            discount_amount=Decimal("0.00"),
            total_amount=Decimal("117500.00"),
            status=Order.Status.SHIPPED,
        )

        self.payment = Payment.objects.create(
            order=self.order,
            payment_method=self.method,
            payment_reference="PAY-COMPLETE-001",
            payment_amount=self.order.total_amount,
            payment_status=Payment.Status.SUCCESS,
            paid_at=timezone.now(),
        )

    def _confirm(self, **changes):
        arguments = {
            "user": self.user,
            "order_id": self.order.pk,
        }
        arguments.update(changes)

        return confirm_order_received(**arguments)

    def test_shipped_order_can_be_completed(self):
        order = self._confirm()

        self.assertEqual(order.status, Order.Status.COMPLETED)

        self.order.refresh_from_db()
        self.assertEqual(
            self.order.status,
            Order.Status.COMPLETED,
        )

        event = self.order.trackings.get(
            status_code=OrderTracking.StatusCode.DELIVERED,
        )

        self.assertTrue(event.is_completed)
        self.assertIsNotNone(event.event_time)

    def test_login_is_required(self):
        with self.assertRaisesMessage(ValidationError, "login"):
            self._confirm(user=AnonymousUser())

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.SHIPPED)

    def test_other_user_cannot_confirm(self):
        with self.assertRaisesMessage(
            ValidationError,
            "Pesanan tidak ditemukan",
        ):
            self._confirm(user=self.other_user)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.SHIPPED)
        self.assertEqual(self.order.trackings.count(), 0)

    def test_non_shipped_orders_are_rejected(self):
        statuses = (
            Order.Status.TO_PAY,
            Order.Status.PROCESSING,
            Order.Status.CANCELLED,
        )

        for status in statuses:
            with self.subTest(status=status):
                self.order.status = status
                self.order.save(update_fields=["status"])

                with self.assertRaisesMessage(
                    ValidationError,
                    "berstatus shipped",
                ):
                    self._confirm()

                self.order.refresh_from_db()
                self.assertEqual(self.order.status, status)
                self.assertEqual(self.order.trackings.count(), 0)

    def test_successful_payment_is_required(self):
        statuses = (
            Payment.Status.PENDING,
            Payment.Status.FAILED,
            Payment.Status.EXPIRED,
        )

        for status in statuses:
            with self.subTest(payment_status=status):
                self.payment.payment_status = status
                self.payment.paid_at = None
                self.payment.save(
                    update_fields=["payment_status", "paid_at"],
                )

                with self.assertRaisesMessage(
                    ValidationError,
                    "Pembayaran pesanan",
                ):
                    self._confirm()

                self.order.refresh_from_db()
                self.assertEqual(
                    self.order.status,
                    Order.Status.SHIPPED,
                )
                self.assertEqual(self.order.trackings.count(), 0)

    def test_payment_amount_must_match_order_total(self):
        self.payment.payment_amount = Decimal("1.00")
        self.payment.save(update_fields=["payment_amount"])

        with self.assertRaisesMessage(
            ValidationError,
            "nominalnya tidak sesuai",
        ):
            self._confirm()

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.SHIPPED)
        self.assertEqual(self.order.trackings.count(), 0)

    def test_repeated_confirmation_does_not_duplicate_tracking(self):
        self._confirm()
        order = self._confirm()

        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertEqual(
            self.order.trackings.filter(
                status_code=OrderTracking.StatusCode.DELIVERED,
            ).count(),
            1,
        )

    def test_tracking_failure_rolls_back_order_status(self):
        with patch(
            "transactions.services.OrderTracking.objects.create",
            side_effect=RuntimeError("Pelacakan gagal disimpan."),
        ):
            with self.assertRaisesMessage(
                RuntimeError,
                "Pelacakan gagal disimpan",
            ):
                self._confirm()

        self.order.refresh_from_db()

        self.assertEqual(self.order.status, Order.Status.SHIPPED)
        self.assertEqual(self.order.trackings.count(), 0)

class CartServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            email="cart@example.com",
            full_name="Pembeli Keranjang",
        )
        self.other_user = User.objects.create_user(
            email="cart-other@example.com",
            full_name="Pembeli Lain",
        )

        category = Category.objects.create(name="Elektronik")
        brand = Brand.objects.create(name="Brand Uji")

        self.product = Product.objects.create(
            category=category,
            brand=brand,
            name="Produk Uji",
            price=Decimal("100000.00"),
        )

        self.variant = ProductVariant.objects.create(
            product=self.product,
            color_name="Hitam",
            stock=10,
            sku="CART-HITAM-001",
        )

    def _add(self, quantity=1, **changes):
        arguments = {
            "user": self.user,
            "product_variant_id": self.variant.pk,
            "quantity": quantity,
        }
        arguments.update(changes)

        return add_cart_item(**arguments)

    def test_new_item_is_added_without_reducing_stock(self):
        item, created = self._add(2)

        self.assertTrue(created)
        self.assertEqual(item.user_id, self.user.pk)
        self.assertEqual(item.product_variant_id, self.variant.pk)
        self.assertEqual(item.quantity, 2)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 10)

    def test_same_variant_adds_quantity_and_checks_combined_stock(self):
        first, _ = self._add(2)
        second, created = self._add(3)

        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.quantity, 5)
        self.assertEqual(Cart.objects.count(), 1)

        with self.assertRaisesMessage(ValidationError, "stok"):
            self._add(6)

        first.refresh_from_db()
        self.assertEqual(first.quantity, 5)

    def test_invalid_quantities_are_rejected(self):
        item, _ = self._add(2)

        invalid_quantities = (
            0, -1, True, False, "2", 1.5, None, 2**31,
        )

        for quantity in invalid_quantities:
            with self.subTest(quantity=quantity):
                with self.assertRaisesMessage(
                    ValidationError,
                    "Jumlah",
                ):
                    self._add(quantity)

                with self.assertRaisesMessage(
                    ValidationError,
                    "Jumlah",
                ):
                    set_cart_item_quantity(
                        user=self.user,
                        cart_item_id=item.pk,
                        quantity=quantity,
                    )

        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)
        self.assertEqual(Cart.objects.count(), 1)

    def test_stock_is_checked_again_when_quantity_changes(self):
        self.variant.stock = 0
        self.variant.save(update_fields=["stock"])

        with self.assertRaisesMessage(ValidationError, "stok"):
            self._add()

        self.assertEqual(Cart.objects.count(), 0)

        self.variant.stock = 10
        self.variant.save(update_fields=["stock"])
        item, _ = self._add(2)

        # Stok berubah setelah item masuk keranjang.
        self.variant.stock = 1
        self.variant.save(update_fields=["stock"])

        with self.assertRaisesMessage(ValidationError, "stok"):
            set_cart_item_quantity(
                user=self.user,
                cart_item_id=item.pk,
                quantity=2,
            )

        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)

        updated = set_cart_item_quantity(
            user=self.user,
            cart_item_id=item.pk,
            quantity=1,
        )
        self.assertEqual(updated.quantity, 1)

    def test_list_only_contains_own_items(self):
        own_item, _ = self._add(2)
        self._add(3, user=self.other_user)

        items = list(get_cart_items(user=self.user))

        self.assertEqual(
            [item.pk for item in items],
            [own_item.pk],
        )
        self.assertEqual(
            items[0].product_variant.product.price,
            Decimal("100000.00"),
        )

    def test_update_and_remove_require_ownership(self):
        item, _ = self._add(2)

        with self.assertRaisesMessage(
            ValidationError,
            "Item keranjang tidak ditemukan",
        ):
            set_cart_item_quantity(
                user=self.other_user,
                cart_item_id=item.pk,
                quantity=1,
            )

        with self.assertRaisesMessage(
            ValidationError,
            "Item keranjang tidak ditemukan",
        ):
            remove_cart_item(
                user=self.other_user,
                cart_item_id=item.pk,
            )

        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)

        updated = set_cart_item_quantity(
            user=self.user,
            cart_item_id=item.pk,
            quantity=4,
        )
        self.assertEqual(updated.quantity, 4)

        remove_cart_item(
            user=self.user,
            cart_item_id=item.pk,
        )
        self.assertFalse(Cart.objects.exists())

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 10)

    def test_login_is_required_for_all_cart_services(self):
        item, _ = self._add(2)

        calls = (
            (get_cart_items, {}),
            (
                add_cart_item,
                {
                    "product_variant_id": self.variant.pk,
                    "quantity": 1,
                },
            ),
            (
                set_cart_item_quantity,
                {
                    "cart_item_id": item.pk,
                    "quantity": 1,
                },
            ),
            (
                remove_cart_item,
                {"cart_item_id": item.pk},
            ),
        )

        for service, arguments in calls:
            with self.subTest(service=service.__name__):
                with self.assertRaisesMessage(
                    ValidationError,
                    "login",
                ):
                    service(user=AnonymousUser(), **arguments)

        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)

    def test_missing_variant_is_rejected(self):
        ProductVariant.objects.filter(pk=self.variant.pk).delete()

        with self.assertRaisesMessage(
            ValidationError,
            "Varian produk tidak ditemukan",
        ):
            self._add()

        self.assertEqual(Cart.objects.count(), 0)

class CartViewTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            email="cart-view@example.com",
            full_name="Pembeli Keranjang",
        )
        self.other_user = User.objects.create_user(
            email="cart-view-other@example.com",
            full_name="Pembeli Lain",
        )

        category = Category.objects.create(
            name="Kategori Keranjang API",
        )
        brand = Brand.objects.create(name="Brand Keranjang API")

        self.product = Product.objects.create(
            category=category,
            brand=brand,
            name="Produk Keranjang API",
            price=Decimal("100000.00"),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            color_name="Hitam",
            stock=10,
            sku="CART-API-HITAM-001",
        )

        self.url = "/api/cart/"

    def _make_item(self, *, quantity=2, user=None):
        return Cart.objects.create(
            user=self.user if user is None else user,
            product_variant=self.variant,
            quantity=quantity,
        )

    def _item_url(self, item):
        return f"/api/cart/{item.pk}/"

    def _json(self, method, url, data):
        return getattr(self.client, method)(
            url,
            data=data,
            content_type="application/json",
        )

    def test_owner_can_add_update_and_remove_items(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["items"], [])
        self.assertEqual(response.json()["data"]["subtotal"], "0.00")

        response = self._json("post", self.url, {
            "product_variant_id": self.variant.pk,
            "quantity": 2,
        })
        self.assertEqual(response.status_code, 201)

        data = response.json()["data"]
        item_id = data["items"][0]["id"]
        item_url = f"/api/cart/{item_id}/"

        self.assertEqual(data["subtotal"], "200000.00")

        response = self._json("post", self.url, {
            "product_variant_id": self.variant.pk,
            "quantity": 3,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["data"]["items"][0]["quantity"],
            5,
        )
        self.assertEqual(Cart.objects.count(), 1)

        response = self._json("patch", item_url, {"quantity": 4})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["data"]["subtotal"],
            "400000.00",
        )
        self.assertEqual(
            response.json()["data"]["total_quantity"],
            4,
        )

        response = self._json("delete", item_url, {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["items"], [])
        self.assertEqual(response.json()["data"]["subtotal"], "0.00")
        self.assertFalse(Cart.objects.exists())

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 10)

    def test_list_only_shows_own_items_and_current_server_prices(self):
        own_item = self._make_item(quantity=2)
        self._make_item(quantity=3, user=self.other_user)

        # Harga berubah setelah item masuk keranjang.
        self.product.price = Decimal("125000.00")
        self.product.save(update_fields=["price"])

        self.client.force_login(self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]

        self.assertEqual(
            [item["id"] for item in data["items"]],
            [own_item.pk],
        )
        self.assertEqual(
            data["items"][0]["unit_price"],
            "125000.00",
        )
        self.assertEqual(data["subtotal"], "250000.00")
        self.assertEqual(data["total_quantity"], 2)
        self.assertFalse(data["has_stock_issue"])

    def test_cart_reports_and_validates_current_stock(self):
        item = self._make_item(quantity=5)

        self.variant.stock = 3
        self.variant.save(update_fields=["stock"])

        self.client.force_login(self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]

        self.assertTrue(data["has_stock_issue"])
        self.assertFalse(data["items"][0]["is_available"])
        self.assertEqual(data["items"][0]["quantity"], 5)
        self.assertEqual(data["items"][0]["stock"], 3)

        response = self._json(
            "patch",
            self._item_url(item),
            {"quantity": 4},
        )
        self.assertEqual(response.status_code, 400)

        item.refresh_from_db()
        self.assertEqual(item.quantity, 5)

        response = self._json(
            "patch",
            self._item_url(item),
            {"quantity": 3},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["data"]["has_stock_issue"])

    def test_add_cannot_exceed_combined_stock(self):
        item = self._make_item(quantity=8)
        self.client.force_login(self.user)

        response = self._json("post", self.url, {
            "product_variant_id": self.variant.pk,
            "quantity": 3,
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn("stok", response.json()["message"])

        item.refresh_from_db()
        self.assertEqual(item.quantity, 8)
        self.assertEqual(Cart.objects.count(), 1)

    def test_login_is_required(self):
        item = self._make_item()

        self.assertEqual(
            self.client.get(self.url).status_code,
            401,
        )

        requests = (
            (
                "post",
                self.url,
                {
                    "product_variant_id": self.variant.pk,
                    "quantity": 1,
                },
            ),
            ("patch", self._item_url(item), {"quantity": 1}),
            ("delete", self._item_url(item), {}),
        )

        for method, url, payload in requests:
            with self.subTest(method=method):
                response = self._json(method, url, payload)
                self.assertEqual(response.status_code, 401)

        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)

    def test_other_user_cannot_change_or_remove_item(self):
        item = self._make_item()
        self.client.force_login(self.other_user)

        for method, payload in (
            ("patch", {"quantity": 1}),
            ("delete", {}),
        ):
            with self.subTest(method=method):
                response = self._json(
                    method,
                    self._item_url(item),
                    payload,
                )
                self.assertEqual(response.status_code, 404)

        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)

    def test_invalid_requests_are_rejected(self):
        item = self._make_item()
        item_url = self._item_url(item)
        self.client.force_login(self.user)

        invalid_requests = (
            ("post", self.url, b'{"product_variant_id":'),
            ("post", self.url, b"[]"),
            ("post", self.url, {}),
            (
                "post", self.url,
                {"product_variant_id": True, "quantity": 1},
            ),
            (
                "post", self.url,
                {"product_variant_id": 2**63, "quantity": 1},
            ),
            (
                "post", self.url,
                {
                    "product_variant_id": self.variant.pk,
                    "quantity": 0,
                },
            ),
            (
                "post", self.url,
                {
                    "product_variant_id": self.variant.pk,
                    "quantity": 1,
                    "unit_price": "1.00",
                },
            ),
            ("patch", item_url, {"quantity": True}),
            (
                "patch", item_url,
                {"quantity": 1, "user_id": self.other_user.pk},
            ),
        )

        for method, url, payload in invalid_requests:
            with self.subTest(method=method, payload=payload):
                response = self._json(method, url, payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn("message", response.json())

        for method, url in (
            ("post", self.url),
            ("patch", item_url),
        ):
            with self.subTest(method=method, content_type="text/plain"):
                response = getattr(self.client, method)(
                    url,
                    data="quantity=1",
                    content_type="text/plain",
                )
                self.assertEqual(response.status_code, 415)

        self.assertEqual(self.client.get(item_url).status_code, 405)
        self.assertEqual(self.client.delete(self.url).status_code, 405)

        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)
        self.assertEqual(Cart.objects.count(), 1)

    def test_csrf_is_required_for_cart_changes(self):
        item = self._make_item()

        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        requests = (
            (
                "post",
                self.url,
                {
                    "product_variant_id": self.variant.pk,
                    "quantity": 1,
                },
            ),
            ("patch", self._item_url(item), {"quantity": 4}),
            ("delete", self._item_url(item), {}),
        )

        # Token contoh khusus pengujian.
        csrf_token = "a" * 32

        for method, url, payload in requests:
            with self.subTest(method=method):
                response = getattr(client, method)(
                    url,
                    data=payload,
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 403)

                client.cookies[settings.CSRF_COOKIE_NAME] = csrf_token

                response = getattr(client, method)(
                    url,
                    data=payload,
                    content_type="application/json",
                    headers={"X-CSRFToken": csrf_token},
                )
                self.assertEqual(response.status_code, 200)

        self.assertFalse(Cart.objects.exists())

class CartViewTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            email="cart-view@example.com",
            full_name="Pembeli Keranjang",
        )
        self.other_user = User.objects.create_user(
            email="cart-view-other@example.com",
            full_name="Pembeli Lain",
        )

        category = Category.objects.create(
            name="Kategori Keranjang API",
        )
        brand = Brand.objects.create(name="Brand Keranjang API")

        self.product = Product.objects.create(
            category=category,
            brand=brand,
            name="Produk Keranjang API",
            price=Decimal("100000.00"),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            color_name="Hitam",
            stock=10,
            sku="CART-API-HITAM-001",
        )

        self.url = "/api/cart/"

    def _make_item(self, *, quantity=2, user=None):
        return Cart.objects.create(
            user=self.user if user is None else user,
            product_variant=self.variant,
            quantity=quantity,
        )

    def _item_url(self, item):
        return f"/api/cart/{item.pk}/"

    def _json(self, method, url, data):
        return getattr(self.client, method)(
            url,
            data=data,
            content_type="application/json",
        )

    def test_owner_can_add_update_and_remove_items(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["items"], [])
        self.assertEqual(response.json()["data"]["subtotal"], "0.00")

        response = self._json("post", self.url, {
            "product_variant_id": self.variant.pk,
            "quantity": 2,
        })
        self.assertEqual(response.status_code, 201)

        data = response.json()["data"]
        item_id = data["items"][0]["id"]
        item_url = f"/api/cart/{item_id}/"

        self.assertEqual(data["subtotal"], "200000.00")

        response = self._json("post", self.url, {
            "product_variant_id": self.variant.pk,
            "quantity": 3,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["data"]["items"][0]["quantity"],
            5,
        )
        self.assertEqual(Cart.objects.count(), 1)

        response = self._json("patch", item_url, {"quantity": 4})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["data"]["subtotal"],
            "400000.00",
        )
        self.assertEqual(
            response.json()["data"]["total_quantity"],
            4,
        )

        response = self._json("delete", item_url, {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["items"], [])
        self.assertEqual(response.json()["data"]["subtotal"], "0.00")
        self.assertFalse(Cart.objects.exists())

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 10)

    def test_list_only_shows_own_items_and_current_server_prices(self):
        own_item = self._make_item(quantity=2)
        self._make_item(quantity=3, user=self.other_user)

        # Harga berubah setelah item masuk keranjang.
        self.product.price = Decimal("125000.00")
        self.product.save(update_fields=["price"])

        self.client.force_login(self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]

        self.assertEqual(
            [item["id"] for item in data["items"]],
            [own_item.pk],
        )
        self.assertEqual(
            data["items"][0]["unit_price"],
            "125000.00",
        )
        self.assertEqual(data["subtotal"], "250000.00")
        self.assertEqual(data["total_quantity"], 2)
        self.assertFalse(data["has_stock_issue"])

    def test_cart_reports_and_validates_current_stock(self):
        item = self._make_item(quantity=5)

        self.variant.stock = 3
        self.variant.save(update_fields=["stock"])

        self.client.force_login(self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]

        self.assertTrue(data["has_stock_issue"])
        self.assertFalse(data["items"][0]["is_available"])
        self.assertEqual(data["items"][0]["quantity"], 5)
        self.assertEqual(data["items"][0]["stock"], 3)

        response = self._json(
            "patch",
            self._item_url(item),
            {"quantity": 4},
        )
        self.assertEqual(response.status_code, 400)

        item.refresh_from_db()
        self.assertEqual(item.quantity, 5)

        response = self._json(
            "patch",
            self._item_url(item),
            {"quantity": 3},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["data"]["has_stock_issue"])

    def test_add_cannot_exceed_combined_stock(self):
        item = self._make_item(quantity=8)
        self.client.force_login(self.user)

        response = self._json("post", self.url, {
            "product_variant_id": self.variant.pk,
            "quantity": 3,
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn("stok", response.json()["message"])

        item.refresh_from_db()
        self.assertEqual(item.quantity, 8)
        self.assertEqual(Cart.objects.count(), 1)

    def test_login_is_required(self):
        item = self._make_item()

        self.assertEqual(
            self.client.get(self.url).status_code,
            401,
        )

        requests = (
            (
                "post",
                self.url,
                {
                    "product_variant_id": self.variant.pk,
                    "quantity": 1,
                },
            ),
            ("patch", self._item_url(item), {"quantity": 1}),
            ("delete", self._item_url(item), {}),
        )

        for method, url, payload in requests:
            with self.subTest(method=method):
                response = self._json(method, url, payload)
                self.assertEqual(response.status_code, 401)

        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)

    def test_other_user_cannot_change_or_remove_item(self):
        item = self._make_item()
        self.client.force_login(self.other_user)

        for method, payload in (
            ("patch", {"quantity": 1}),
            ("delete", {}),
        ):
            with self.subTest(method=method):
                response = self._json(
                    method,
                    self._item_url(item),
                    payload,
                )
                self.assertEqual(response.status_code, 404)

        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)

    def test_invalid_requests_are_rejected(self):
        item = self._make_item()
        item_url = self._item_url(item)
        self.client.force_login(self.user)

        invalid_requests = (
            ("post", self.url, b'{"product_variant_id":'),
            ("post", self.url, b"[]"),
            ("post", self.url, {}),
            (
                "post", self.url,
                {"product_variant_id": True, "quantity": 1},
            ),
            (
                "post", self.url,
                {"product_variant_id": 2**63, "quantity": 1},
            ),
            (
                "post", self.url,
                {
                    "product_variant_id": self.variant.pk,
                    "quantity": 0,
                },
            ),
            (
                "post", self.url,
                {
                    "product_variant_id": self.variant.pk,
                    "quantity": 1,
                    "unit_price": "1.00",
                },
            ),
            ("patch", item_url, {"quantity": True}),
            (
                "patch", item_url,
                {"quantity": 1, "user_id": self.other_user.pk},
            ),
        )

        for method, url, payload in invalid_requests:
            with self.subTest(method=method, payload=payload):
                response = self._json(method, url, payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn("message", response.json())

        for method, url in (
            ("post", self.url),
            ("patch", item_url),
        ):
            with self.subTest(method=method, content_type="text/plain"):
                response = getattr(self.client, method)(
                    url,
                    data="quantity=1",
                    content_type="text/plain",
                )
                self.assertEqual(response.status_code, 415)

        self.assertEqual(self.client.get(item_url).status_code, 405)
        self.assertEqual(self.client.delete(self.url).status_code, 405)

        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)
        self.assertEqual(Cart.objects.count(), 1)

    def test_csrf_is_required_for_cart_changes(self):
        item = self._make_item()

        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        requests = (
            (
                "post",
                self.url,
                {
                    "product_variant_id": self.variant.pk,
                    "quantity": 1,
                },
            ),
            ("patch", self._item_url(item), {"quantity": 4}),
            ("delete", self._item_url(item), {}),
        )

        # Token contoh khusus pengujian.
        csrf_token = "a" * 32

        for method, url, payload in requests:
            with self.subTest(method=method):
                response = getattr(client, method)(
                    url,
                    data=payload,
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 403)

                client.cookies[settings.CSRF_COOKIE_NAME] = csrf_token

                response = getattr(client, method)(
                    url,
                    data=payload,
                    content_type="application/json",
                    headers={"X-CSRFToken": csrf_token},
                )
                self.assertEqual(response.status_code, 200)

        self.assertFalse(Cart.objects.exists())

class CartPromoViewTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            email="cart-promo@example.com",
            full_name="Pembeli Promo",
        )
        self.other_user = User.objects.create_user(
            email="cart-promo-other@example.com",
            full_name="Pembeli Lain",
        )

        category = Category.objects.create(name="Kategori Promo")
        brand = Brand.objects.create(name="Brand Promo")

        self.product = Product.objects.create(
            category=category,
            brand=brand,
            name="Produk Promo",
            price=Decimal("100000.00"),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            color_name="Hitam",
            stock=10,
            sku="CART-PROMO-HITAM-001",
        )

        self.item = Cart.objects.create(
            user=self.user,
            product_variant=self.variant,
            quantity=2,
        )

        self.promo = PromoCode.objects.create(
            code="HEMAT10",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("10.00"),
            max_discount=Decimal("50000.00"),
            min_order_amount=Decimal("100000.00"),
            quota_total=100,
            quota_per_user=1,
            expires_at=timezone.now() + timedelta(days=7),
        )

        self.url = "/api/promo-codes/validate/"

    def _post(self, data=None):
        if data is None:
            data = {"code": self.promo.code}

        return self.client.post(
            self.url,
            data=data,
            content_type="application/json",
        )

    def test_uses_own_cart_and_current_prices(self):
        Cart.objects.create(
            user=self.other_user,
            product_variant=self.variant,
            quantity=7,
        )

        self.product.price = Decimal("125000.00")
        self.product.save(update_fields=["price"])

        self.client.force_login(self.user)
        response = self._post()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["data"],
            {
                "code": "HEMAT10",
                "subtotal": "250000.00",
                "discount_amount": "25000.00",
                "subtotal_after_discount": "225000.00",
            },
        )

    def test_empty_cart_is_rejected(self):
        self.item.delete()

        # Keranjang pengguna lain tetap tidak boleh ikut dihitung.
        Cart.objects.create(
            user=self.other_user,
            product_variant=self.variant,
            quantity=1,
        )

        self.client.force_login(self.user)
        response = self._post()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["message"],
            "Keranjang masih kosong.",
        )

    def test_invalid_cart_is_rejected(self):
        self.client.force_login(self.user)

        self.variant.stock = 1
        self.variant.save(update_fields=["stock"])

        response = self._post()

        self.assertEqual(response.status_code, 400)
        self.assertIn("Stok", response.json()["message"])

        self.variant.stock = 10
        self.variant.save(update_fields=["stock"])

        self.product.price = Decimal("-1.00")
        self.product.save(update_fields=["price"])

        response = self._post()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["message"],
            "Harga produk tidak valid.",
        )

    def test_expired_promo_returns_json_error(self):
        self.promo.expires_at = (
            timezone.now() - timedelta(seconds=1)
        )
        self.promo.save(update_fields=["expires_at"])

        self.client.force_login(self.user)
        response = self._post()

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "kedaluwarsa",
            response.json()["message"],
        )

    def test_preview_does_not_consume_quota(self):
        self.promo.quota_total = 1
        self.promo.save(update_fields=["quota_total"])

        initial_order_count = Order.objects.count()
        self.client.force_login(self.user)

        for attempt in range(2):
            with self.subTest(attempt=attempt):
                response = self._post()
                self.assertEqual(response.status_code, 200)

        self.assertEqual(
            Order.objects.count(),
            initial_order_count,
        )

        self.item.refresh_from_db()
        self.variant.refresh_from_db()

        self.assertEqual(self.item.quantity, 2)
        self.assertEqual(self.variant.stock, 10)

    def test_login_is_required(self):
        response = self._post()

        self.assertEqual(response.status_code, 401)

    def test_invalid_requests_are_rejected(self):
        self.client.force_login(self.user)

        payloads = (
            b'{"code":',
            b"[]",
            b"null",
            {},
            {"code": None},
            {"code": 123},
            {"code": " "},
            {"code": "X" * 51},
            {
                "code": self.promo.code,
                "subtotal": "1.00",
            },
            {
                "code": self.promo.code,
                "user_id": self.other_user.pk,
            },
        )

        for payload in payloads:
            with self.subTest(payload=payload):
                response = self._post(data=payload)

                self.assertEqual(response.status_code, 400)
                self.assertIn("message", response.json())

        response = self.client.post(
            self.url,
            data="code=HEMAT10",
            content_type="text/plain",
        )
        self.assertEqual(response.status_code, 415)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_csrf_is_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        payload = {"code": self.promo.code}

        response = client.post(
            self.url,
            data=payload,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

        # Token contoh khusus pengujian.
        csrf_token = "a" * 32
        client.cookies[settings.CSRF_COOKIE_NAME] = csrf_token

        response = client.post(
            self.url,
            data=payload,
            content_type="application/json",
            headers={"X-CSRFToken": csrf_token},
        )
        self.assertEqual(response.status_code, 200)

class OrderCompletionViewTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            email="complete-view@example.com",
            full_name="Pemilik Pesanan",
        )
        self.other_user = User.objects.create_user(
            email="complete-view-other@example.com",
            full_name="Pengguna Lain",
        )

        shipping = ShippingMethod.objects.create(
            name="Reguler",
            estimated_days="2-4 hari",
            base_cost=Decimal("15000.00"),
        )
        method = PaymentMethod.objects.create(
            name="Transfer Bank",
            channel_provider="Manual",
            service_fee=Decimal("2500.00"),
        )

        self.order = Order.objects.create(
            order_number="COMPLETE-VIEW-001",
            user=self.user,
            shipping_method=shipping,
            shipping_address_snapshot="Alamat pengujian, Jember",
            subtotal=Decimal("100000.00"),
            shipping_fee=Decimal("15000.00"),
            service_fee=Decimal("2500.00"),
            total_amount=Decimal("117500.00"),
            status=Order.Status.SHIPPED,
        )

        self.payment = Payment.objects.create(
            order=self.order,
            payment_method=method,
            payment_reference="PAY-COMPLETE-VIEW-001",
            payment_amount=self.order.total_amount,
            payment_status=Payment.Status.SUCCESS,
            paid_at=timezone.now(),
        )

        self.url = f"/api/orders/{self.order.pk}/complete/"

    def test_owner_can_confirm_receipt(self):
        self.client.force_login(self.user)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["data"],
            {
                "id": self.order.pk,
                "order_number": "COMPLETE-VIEW-001",
                "status": Order.Status.COMPLETED,
            },
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.COMPLETED)

        self.assertTrue(
            self.order.trackings.filter(
                status_code=OrderTracking.StatusCode.DELIVERED,
                is_completed=True,
            ).exists()
        )

    def test_login_is_required(self):
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 401)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.SHIPPED)

    def test_other_user_cannot_confirm(self):
        self.client.force_login(self.other_user)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 404)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.SHIPPED)
        self.assertEqual(self.order.trackings.count(), 0)

    def test_invalid_status_or_unpaid_order_is_rejected(self):
        self.client.force_login(self.user)

        cases = (
            (Order.Status.PROCESSING, Payment.Status.SUCCESS),
            (Order.Status.SHIPPED, Payment.Status.PENDING),
        )

        for order_status, payment_status in cases:
            with self.subTest(
                order_status=order_status,
                payment_status=payment_status,
            ):
                self.order.status = order_status
                self.order.save(update_fields=["status"])

                self.payment.payment_status = payment_status
                self.payment.paid_at = (
                    timezone.now()
                    if payment_status == Payment.Status.SUCCESS
                    else None
                )
                self.payment.save(
                    update_fields=["payment_status", "paid_at"],
                )

                response = self.client.post(self.url)

                self.assertEqual(response.status_code, 400)
                self.assertIn("message", response.json())

                self.order.refresh_from_db()
                self.assertEqual(self.order.status, order_status)
                self.assertEqual(self.order.trackings.count(), 0)

    def test_repeated_confirmation_does_not_duplicate_tracking(self):
        self.client.force_login(self.user)

        first = self.client.post(self.url)
        second = self.client.post(self.url)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            first.json()["data"],
            second.json()["data"],
        )

        self.assertEqual(
            self.order.trackings.filter(
                status_code=OrderTracking.StatusCode.DELIVERED,
            ).count(),
            1,
        )

    def test_get_is_rejected_without_changing_order(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.SHIPPED)
        self.assertEqual(self.order.trackings.count(), 0)

    def test_csrf_is_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        response = client.post(self.url)

        self.assertEqual(response.status_code, 403)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.SHIPPED)
        self.assertEqual(self.order.trackings.count(), 0)

        # Token contoh khusus pengujian.
        csrf_token = "a" * 32
        client.cookies[settings.CSRF_COOKIE_NAME] = csrf_token

        response = client.post(
            self.url,
            headers={"X-CSRFToken": csrf_token},
        )

        self.assertEqual(response.status_code, 200)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.COMPLETED)

class OrderItemSnapshotTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            email="order-items@example.com",
            full_name="Pemilik Pesanan",
        )
        self.other_user = User.objects.create_user(
            email="order-items-other@example.com",
            full_name="Pengguna Lain",
        )

        category = Category.objects.create(name="Kategori Order Item")
        brand = Brand.objects.create(name="Brand Order Item")

        self.product = Product.objects.create(
            category=category,
            brand=brand,
            name="Produk Saat Dibeli",
            price=Decimal("50000.00"),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            color_name="Hitam",
            stock=10,
            sku="ORDER-ITEM-HITAM-001",
        )

        self.shipping = ShippingMethod.objects.create(
            name="Reguler",
            estimated_days="2-4 hari",
            base_cost=Decimal("15000.00"),
        )

        self.order = self._make_order(self.user, "ITEM-ORDER-001")
        self.item = self._make_item(self.order)
        self.detail_url = f"/api/orders/{self.order.pk}/"

    def _make_order(self, user, number):
        return Order.objects.create(
            order_number=number,
            user=user,
            shipping_method=self.shipping,
            shipping_address_snapshot="Alamat saat pembelian",
            subtotal=Decimal("100000.00"),
            shipping_fee=Decimal("15000.00"),
            service_fee=Decimal("2500.00"),
            total_amount=Decimal("117500.00"),
        )

    def _make_item(self, order):
        return OrderItem.objects.create(
            order=order,
            product_variant=self.variant,
            product_name_snapshot="Produk Saat Dibeli",
            variant_name_snapshot="Hitam",
            sku_snapshot="ORDER-ITEM-HITAM-001",
            quantity=2,
            price_at_purchase=Decimal("50000.00"),
        )

    def test_detail_contains_purchased_items(self):
        self.client.force_login(self.user)

        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 200)
        items = response.json()["data"]["items"]

        self.assertEqual(len(items), 1)
        self.assertEqual(
            items[0],
            {
                "id": self.item.pk,
                "product_variant_id": self.variant.pk,
                "product_name": "Produk Saat Dibeli",
                "variant_name": "Hitam",
                "sku": "ORDER-ITEM-HITAM-001",
                "quantity": 2,
                "unit_price": "50000.00",
                "line_total": "100000.00",
            },
        )

    def test_history_contains_only_own_purchased_items(self):
        other_order = self._make_order(
            self.other_user,
            "ITEM-OTHER-001",
        )
        self._make_item(other_order)

        self.client.force_login(self.user)
        response = self.client.get("/api/orders/")

        self.assertEqual(response.status_code, 200)
        orders = response.json()["data"]

        self.assertEqual(
            [order["id"] for order in orders],
            [self.order.pk],
        )
        self.assertEqual(
            [item["id"] for item in orders[0]["items"]],
            [self.item.pk],
        )

    def test_catalog_changes_do_not_change_purchase_information(self):
        self.product.name = "Nama Produk Baru"
        self.product.price = Decimal("900000.00")
        self.product.save(update_fields=["name", "price"])

        self.variant.color_name = "Putih"
        self.variant.sku = "SKU-BARU-001"
        self.variant.save(update_fields=["color_name", "sku"])

        self.client.force_login(self.user)
        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 200)
        item = response.json()["data"]["items"][0]

        self.assertEqual(item["product_name"], "Produk Saat Dibeli")
        self.assertEqual(item["variant_name"], "Hitam")
        self.assertEqual(item["sku"], "ORDER-ITEM-HITAM-001")
        self.assertEqual(item["unit_price"], "50000.00")
        self.assertEqual(item["line_total"], "100000.00")

    def test_product_deletion_preserves_order_items(self):
        self.product.delete()

        self.item.refresh_from_db()
        self.assertIsNone(self.item.product_variant_id)

        self.client.force_login(self.user)
        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 200)
        item = response.json()["data"]["items"][0]

        self.assertIsNone(item["product_variant_id"])
        self.assertEqual(item["product_name"], "Produk Saat Dibeli")
        self.assertEqual(item["quantity"], 2)
        self.assertEqual(item["unit_price"], "50000.00")
        self.assertEqual(item["line_total"], "100000.00")
        self.assertEqual(OrderItem.objects.count(), 1)

    def test_other_user_cannot_view_purchased_items(self):
        self.client.force_login(self.other_user)

        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 404)

        response = self.client.get("/api/orders/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], [])

    def test_database_rejects_invalid_quantity_or_price(self):
        invalid_values = (
            {
                "quantity": 0,
                "price_at_purchase": Decimal("50000.00"),
            },
            {
                "quantity": 2,
                "price_at_purchase": Decimal("-1.00"),
            },
        )

        for values in invalid_values:
            with self.subTest(values=values):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        OrderItem.objects.create(
                            order=self.order,
                            product_variant=self.variant,
                            product_name_snapshot="Item Tidak Valid",
                            variant_name_snapshot="Hitam",
                            sku_snapshot="INVALID-ITEM",
                            **values,
                        )

        self.assertEqual(OrderItem.objects.count(), 1)

class CheckoutServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            email="checkout@example.com",
            full_name="Pembeli Checkout",
        )
        self.other_user = User.objects.create_user(
            email="checkout-other@example.com",
            full_name="Pembeli Lain",
        )

        self.address = self._make_address(
            self.user,
            is_main=True,
        )

        category = Category.objects.create(name="Kategori Checkout")
        brand = Brand.objects.create(name="Brand Checkout")

        self.product = Product.objects.create(
            category=category,
            brand=brand,
            name="Produk Checkout",
            price=Decimal("100000.00"),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            color_name="Hitam",
            stock=10,
            sku="CHECKOUT-HITAM-001",
        )

        self.cart_item = Cart.objects.create(
            user=self.user,
            product_variant=self.variant,
            quantity=2,
        )
        self.other_item = Cart.objects.create(
            user=self.other_user,
            product_variant=self.variant,
            quantity=3,
        )

        self.shipping = ShippingMethod.objects.create(
            name="Reguler",
            estimated_days="2-4 hari",
            base_cost=Decimal("15000.00"),
        )
        self.method = PaymentMethod.objects.create(
            name="Transfer Bank",
            channel_provider="Manual",
            service_fee=Decimal("2500.00"),
        )

        self.promo = PromoCode.objects.create(
            code="HEMAT10",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("10.00"),
            max_discount=Decimal("50000.00"),
            min_order_amount=Decimal("100000.00"),
            quota_total=100,
            quota_per_user=1,
            expires_at=timezone.now() + timedelta(days=7),
        )

        self.key = uuid4()

    def _make_address(self, user, **changes):
        values = {
            "user": user,
            "label": "Rumah",
            "recipient_name": "Penerima Uji",
            "recipient_phone": "081234567890",
            "street_address": "Jalan Contoh No. 1",
            "subdistrict": "Kaliwates",
            "city": "Jember",
            "province": "Jawa Timur",
            "postal_code": "68111",
        }
        values.update(changes)

        return UserAddress.objects.create(**values)

    def _checkout(self, **changes):
        arguments = {
            "user": self.user,
            "checkout_key": self.key,
            "address_id": self.address.pk,
            "shipping_method_id": self.shipping.pk,
            "payment_method_id": self.method.pk,
            "promo_code": None,
        }
        arguments.update(changes)

        return checkout_cart(**arguments)

    def _assert_no_checkout(self, *, stock=10, orders=0, empty=False):
        self.assertEqual(Order.objects.count(), orders)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(OrderTracking.objects.count(), 0)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, stock)

        if empty:
            self.assertFalse(
                Cart.objects.filter(user=self.user).exists()
            )
        else:
            self.cart_item.refresh_from_db()
            self.assertEqual(self.cart_item.quantity, 2)

        self.other_item.refresh_from_db()
        self.assertEqual(self.other_item.quantity, 3)

    def test_checkout_creates_order_items_payment_and_tracking(self):
        order, created = self._checkout()

        self.assertTrue(created)
        self.assertEqual(order.user_id, self.user.pk)
        self.assertEqual(order.status, Order.Status.TO_PAY)
        self.assertEqual(order.subtotal, Decimal("200000.00"))
        self.assertEqual(order.shipping_fee, Decimal("15000.00"))
        self.assertEqual(order.service_fee, Decimal("2500.00"))
        self.assertEqual(order.total_amount, Decimal("217500.00"))
        self.assertTrue(order.stock_deducted)

        for value in (
            self.address.recipient_name,
            self.address.recipient_phone,
            self.address.street_address,
            self.address.subdistrict,
            self.address.city,
            self.address.province,
            self.address.postal_code,
        ):
            self.assertIn(value, order.shipping_address_snapshot)

        item = order.items.get()
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.price_at_purchase, Decimal("100000.00"))
        self.assertEqual(item.sku_snapshot, "CHECKOUT-HITAM-001")

        payment = order.payments.get()
        self.assertEqual(payment.payment_status, Payment.Status.PENDING)
        self.assertEqual(payment.payment_amount, order.total_amount)
        self.assertEqual(payment.expires_at, order.payment_due_at)
        self.assertGreater(order.payment_due_at, timezone.now())

        self.assertTrue(
            order.trackings.filter(
                status_code=OrderTracking.StatusCode.ORDER_PLACED,
                is_completed=True,
            ).exists()
        )

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 8)
        self.assertFalse(Cart.objects.filter(user=self.user).exists())

        self.other_item.refresh_from_db()
        self.assertEqual(self.other_item.quantity, 3)

    def test_checkout_uses_current_prices_and_promo(self):
        self.product.price = Decimal("125000.00")
        self.product.save(update_fields=["price"])

        order, _ = self._checkout(promo_code=self.promo.code)

        self.assertEqual(order.subtotal, Decimal("250000.00"))
        self.assertEqual(order.discount_amount, Decimal("25000.00"))
        self.assertEqual(order.total_amount, Decimal("242500.00"))
        self.assertEqual(order.promo_code_id, self.promo.pk)
        self.assertEqual(
            order.items.get().price_at_purchase,
            Decimal("125000.00"),
        )

    def test_invalid_address_is_rejected(self):
        foreign_address = self._make_address(self.other_user)

        with self.assertRaisesMessage(ValidationError, "Alamat"):
            self._checkout(address_id=foreign_address.pk)

        self._assert_no_checkout()

        self.address.postal_code = ""
        self.address.save(update_fields=["postal_code"])

        with self.assertRaisesMessage(
            ValidationError,
            "belum lengkap",
        ):
            self._checkout()

        self._assert_no_checkout()

    def test_empty_cart_is_rejected(self):
        self.cart_item.delete()

        with self.assertRaisesMessage(
            ValidationError,
            "Keranjang masih kosong",
        ):
            self._checkout()

        self._assert_no_checkout(empty=True)

    def test_unavailable_stock_or_methods_are_rejected(self):
        self.variant.stock = 1
        self.variant.save(update_fields=["stock"])

        with self.assertRaisesMessage(ValidationError, "Stok"):
            self._checkout()

        self._assert_no_checkout(stock=1)

        self.variant.stock = 10
        self.variant.save(update_fields=["stock"])

        for selected_method in (self.shipping, self.method):
            with self.subTest(model=selected_method._meta.label):
                selected_method.is_active = False
                selected_method.save(update_fields=["is_active"])

                with self.assertRaisesMessage(
                    ValidationError,
                    "tidak tersedia",
                ):
                    self._checkout()

                self._assert_no_checkout()

                selected_method.is_active = True
                selected_method.save(update_fields=["is_active"])

    def test_exhausted_promo_quota_is_rejected(self):
        self.promo.quota_total = 1
        self.promo.save(update_fields=["quota_total"])

        Order.objects.create(
            order_number="QUOTA-ALREADY-USED",
            user=self.other_user,
            shipping_method=self.shipping,
            promo_code=self.promo,
            shipping_address_snapshot="Alamat pengguna lain",
            subtotal=Decimal("200000.00"),
            shipping_fee=Decimal("15000.00"),
            service_fee=Decimal("2500.00"),
            discount_amount=Decimal("20000.00"),
            total_amount=Decimal("197500.00"),
            payment_due_at=timezone.now() + timedelta(hours=24),
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Kuota promo",
        ):
            self._checkout(promo_code=self.promo.code)

        self._assert_no_checkout(orders=1)

    def test_retry_returns_same_order_without_deducting_stock_again(self):
        first, created = self._checkout()
        self.assertTrue(created)

        # Item baru ini harus tetap menjadi keranjang berikutnya.
        new_cart_item = Cart.objects.create(
            user=self.user,
            product_variant=self.variant,
            quantity=1,
        )

        second, created = self._checkout()

        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 8)

        new_cart_item.refresh_from_db()
        self.assertEqual(new_cart_item.quantity, 1)

    def test_key_cannot_be_reused_for_different_request(self):
        self._checkout()

        with self.assertRaisesMessage(
            ValidationError,
            "data yang berbeda",
        ):
            self._checkout(promo_code=self.promo.code)

        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 8)

    def test_snapshots_survive_later_changes(self):
        order, _ = self._checkout()
        saved_address = order.shipping_address_snapshot

        self.address.recipient_name = "Penerima Baru"
        self.address.street_address = "Jalan Baru"
        self.address.save(
            update_fields=["recipient_name", "street_address"],
        )

        self.product.name = "Nama Produk Baru"
        self.product.price = Decimal("900000.00")
        self.product.save(update_fields=["name", "price"])

        self.variant.color_name = "Putih"
        self.variant.sku = "SKU-CHECKOUT-BARU"
        self.variant.save(update_fields=["color_name", "sku"])

        order.refresh_from_db()
        item = order.items.get()

        self.assertEqual(order.shipping_address_snapshot, saved_address)
        self.assertEqual(item.product_name_snapshot, "Produk Checkout")
        self.assertEqual(item.variant_name_snapshot, "Hitam")
        self.assertEqual(item.sku_snapshot, "CHECKOUT-HITAM-001")
        self.assertEqual(item.price_at_purchase, Decimal("100000.00"))

    def test_tracking_failure_rolls_back_everything(self):
        with patch(
            "transactions.services.OrderTracking.objects.create",
            side_effect=RuntimeError("Pencatatan pesanan gagal."),
        ):
            with self.assertRaisesMessage(
                RuntimeError,
                "Pencatatan pesanan gagal",
            ):
                self._checkout()

        self._assert_no_checkout()

    def test_invalid_arguments_and_login_are_rejected(self):
        invalid_arguments = (
            {"user": AnonymousUser()},
            {"checkout_key": "bukan-uuid"},
            {"address_id": True},
            {"shipping_method_id": "1"},
            {"payment_method_id": 0},
            {"promo_code": ""},
        )

        for changes in invalid_arguments:
            with self.subTest(changes=changes):
                with self.assertRaises(ValidationError):
                    self._checkout(**changes)

                self._assert_no_checkout()

    def test_zero_total_is_marked_paid(self):
        self.shipping.base_cost = Decimal("0.00")
        self.shipping.save(update_fields=["base_cost"])

        self.method.service_fee = Decimal("0.00")
        self.method.save(update_fields=["service_fee"])

        self.promo.discount_type = DiscountType.FIXED
        self.promo.discount_value = Decimal("200000.00")
        self.promo.max_discount = None
        self.promo.save()

        order, _ = self._checkout(promo_code=self.promo.code)
        payment = order.payments.get()

        self.assertEqual(order.total_amount, Decimal("0.00"))
        self.assertEqual(order.status, Order.Status.PROCESSING)
        self.assertIsNone(order.payment_due_at)
        self.assertEqual(payment.payment_status, Payment.Status.SUCCESS)
        self.assertEqual(payment.payment_amount, Decimal("0.00"))
        self.assertIsNotNone(payment.paid_at)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 8)

class CheckoutViewTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            email="checkout-http@example.com",
            full_name="Pembeli Checkout HTTP",
        )
        self.other_user = User.objects.create_user(
            email="checkout-http-other@example.com",
            full_name="Pembeli Lain",
        )

        address_data = {
            "label": "Rumah",
            "recipient_name": "Penerima Uji",
            "recipient_phone": "081234567890",
            "street_address": "Jalan Contoh No. 1",
            "subdistrict": "Kaliwates",
            "city": "Jember",
            "province": "Jawa Timur",
            "postal_code": "68111",
        }

        self.address = UserAddress.objects.create(
            user=self.user,
            **address_data,
        )
        self.other_address = UserAddress.objects.create(
            user=self.other_user,
            **address_data,
        )

        category = Category.objects.create(name="Kategori Checkout HTTP")
        brand = Brand.objects.create(name="Brand Checkout HTTP")

        self.product = Product.objects.create(
            category=category,
            brand=brand,
            name="Produk Checkout HTTP",
            price=Decimal("100000.00"),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            color_name="Hitam",
            stock=10,
            sku="CHECKOUT-HTTP-HITAM",
        )

        Cart.objects.create(
            user=self.user,
            product_variant=self.variant,
            quantity=2,
        )
        Cart.objects.create(
            user=self.other_user,
            product_variant=self.variant,
            quantity=1,
        )

        self.shipping = ShippingMethod.objects.create(
            name="Reguler",
            estimated_days="2-4 hari",
            base_cost=Decimal("15000.00"),
        )
        self.method = PaymentMethod.objects.create(
            name="Transfer Bank",
            channel_provider="Manual",
            service_fee=Decimal("2500.00"),
        )

        self.url = "/api/checkout/"
        self.payload = {
            "checkout_key": str(uuid4()),
            "address_id": self.address.pk,
            "shipping_method_id": self.shipping.pk,
            "payment_method_id": self.method.pk,
        }

        self.client.force_login(self.user)

    def _post(self, payload=None):
        return self.client.post(
            self.url,
            data=self.payload if payload is None else payload,
            content_type="application/json",
        )

    def _assert_unchanged(self, stock=10):
        for model in (Order, OrderItem, Payment, OrderTracking):
            self.assertEqual(model.objects.count(), 0)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, stock)

        self.assertEqual(
            Cart.objects.get(user=self.user).quantity,
            2,
        )
        self.assertEqual(
            Cart.objects.get(user=self.other_user).quantity,
            1,
        )

    def _create_promo(self, **changes):
        data = {
            "code": "CHECKOUTHTTP",
            "discount_type": DiscountType.PERCENTAGE,
            "discount_value": Decimal("10.00"),
            "min_order_amount": Decimal("0.00"),
            "quota_total": 100,
            "quota_per_user": 1,
            "expires_at": timezone.now() + timedelta(days=1),
            "is_active": True,
        }
        data.update(changes)
        return PromoCode.objects.create(**data)

    def test_owner_can_checkout(self):
        response = self._post()

        self.assertEqual(response.status_code, 201)
        data = response.json()["data"]

        order = Order.objects.get(pk=data["id"])
        self.assertEqual(order.user_id, self.user.pk)

        self.assertEqual(data["checkout_key"], self.payload["checkout_key"])
        self.assertEqual(data["status"], Order.Status.TO_PAY)
        self.assertEqual(data["subtotal"], "200000.00")
        self.assertEqual(data["shipping_fee"], "15000.00")
        self.assertEqual(data["service_fee"], "2500.00")
        self.assertEqual(data["discount_amount"], "0.00")
        self.assertEqual(data["total_amount"], "217500.00")
        self.assertIsNotNone(data["payment_due_at"])

        self.assertIn(
            self.address.street_address,
            data["shipping_address_snapshot"],
        )

        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["quantity"], 2)
        self.assertEqual(data["items"][0]["unit_price"], "100000.00")
        self.assertEqual(data["items"][0]["line_total"], "200000.00")
        self.assertEqual(data["items"][0]["sku"], self.variant.sku)

        payment = data["payment"]
        self.assertEqual(payment["payment_status"], Payment.Status.PENDING)
        self.assertEqual(payment["payment_amount"], "217500.00")
        self.assertEqual(payment["payment_method_id"], self.method.pk)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 8)
        self.assertFalse(Cart.objects.filter(user=self.user).exists())
        self.assertEqual(
            Cart.objects.get(user=self.other_user).quantity,
            1,
        )

    def test_login_is_required(self):
        self.client.logout()

        response = self._post()

        self.assertEqual(response.status_code, 401)
        self.assertIn("message", response.json())
        self._assert_unchanged()

    def test_get_is_rejected(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)
        self._assert_unchanged()

    def test_non_json_is_rejected(self):
        response = self.client.post(
            self.url,
            data=self.payload,
        )

        self.assertEqual(response.status_code, 415)
        self.assertIn("message", response.json())
        self._assert_unchanged()

    def test_invalid_payloads_are_rejected(self):
        for raw_body in ("{", "[]", "null", '"teks"', "42"):
            with self.subTest(raw_body=raw_body):
                response = self.client.post(
                    self.url,
                    data=raw_body,
                    content_type="application/json",
                )

                self.assertEqual(response.status_code, 400)
                self.assertIn("message", response.json())
                self._assert_unchanged()

        missing_key = self.payload.copy()
        missing_key.pop("checkout_key")

        invalid_payloads = [
            {},
            missing_key,
            {**self.payload, "checkout_key": "bukan-uuid"},
            {**self.payload, "address_id": True},
            {**self.payload, "shipping_method_id": "1"},
            {**self.payload, "payment_method_id": 0},
            {**self.payload, "promo_code": 123},
            {**self.payload, "user_id": self.other_user.pk},
            {**self.payload, "total_amount": "1.00"},
            {**self.payload, "items": []},
            {**self.payload, "payment_status": "SUCCESS"},
        ]

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self._post(payload)

                self.assertEqual(response.status_code, 400)
                self.assertIn("message", response.json())
                self._assert_unchanged()

    def test_other_users_address_is_rejected(self):
        response = self._post({
            **self.payload,
            "address_id": self.other_address.pk,
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn("tidak ditemukan", response.json()["message"])
        self._assert_unchanged()

    def test_service_errors_are_returned_as_json(self):
        self.variant.stock = 1
        self.variant.save(update_fields=["stock"])

        response = self._post()

        self.assertEqual(response.status_code, 400)
        self.assertIn("message", response.json())
        self._assert_unchanged(stock=1)

    def test_retry_is_safe_and_conflicting_request_is_rejected(self):
        first = self._post()
        self.assertEqual(first.status_code, 201)
        order_id = first.json()["data"]["id"]

        # Item baru setelah checkout pertama.
        Cart.objects.create(
            user=self.user,
            product_variant=self.variant,
            quantity=1,
        )

        retry = self._post()

        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json()["data"]["id"], order_id)

        conflict = self._post({
            **self.payload,
            "payment_method_id": self.method.pk + 1000,
        })

        self.assertEqual(conflict.status_code, 400)
        self.assertIn("message", conflict.json())

        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderItem.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(OrderTracking.objects.count(), 1)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 8)

        # Retry tidak menghapus item baru.
        self.assertEqual(
            Cart.objects.get(user=self.user).quantity,
            1,
        )
        self.assertEqual(
            Cart.objects.get(user=self.other_user).quantity,
            1,
        )

    def test_promo_discount_is_calculated_by_server(self):
        promo = self._create_promo()

        response = self._post({
            **self.payload,
            "promo_code": promo.code,
        })

        self.assertEqual(response.status_code, 201)
        data = response.json()["data"]

        self.assertEqual(data["subtotal"], "200000.00")
        self.assertEqual(data["discount_amount"], "20000.00")
        self.assertEqual(data["total_amount"], "197500.00")
        self.assertEqual(
            data["payment"]["payment_amount"],
            "197500.00",
        )

    def test_zero_total_is_returned_as_paid(self):
        self.shipping.base_cost = Decimal("0.00")
        self.shipping.save(update_fields=["base_cost"])

        self.method.service_fee = Decimal("0.00")
        self.method.save(update_fields=["service_fee"])

        promo = self._create_promo(
            discount_type=DiscountType.FIXED,
            discount_value=Decimal("200000.00"),
        )

        response = self._post({
            **self.payload,
            "promo_code": promo.code,
        })

        self.assertEqual(response.status_code, 201)
        data = response.json()["data"]

        self.assertEqual(data["total_amount"], "0.00")
        self.assertEqual(data["status"], Order.Status.PROCESSING)
        self.assertIsNone(data["payment_due_at"])
        self.assertEqual(
            data["payment"]["payment_status"],
            Payment.Status.SUCCESS,
        )
        self.assertEqual(data["payment"]["payment_amount"], "0.00")
        self.assertIsNotNone(data["payment"]["paid_at"])

    def test_csrf_is_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        rejected = client.post(
            self.url,
            data=self.payload,
            content_type="application/json",
        )

        self.assertEqual(rejected.status_code, 403)
        self._assert_unchanged()

        # Nilai tetap ini hanya digunakan untuk tes.
        csrf_token = "a" * 32
        client.cookies[settings.CSRF_COOKIE_NAME] = csrf_token

        accepted = client.post(
            self.url,
            data=self.payload,
            content_type="application/json",
            headers={"X-CSRFToken": csrf_token},
        )

        self.assertEqual(accepted.status_code, 201)
        self.assertEqual(Order.objects.count(), 1)

class OrderCancellationServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            email="cancel-order@example.com",
            full_name="Pembeli Pembatalan",
        )
        self.other_user = User.objects.create_user(
            email="cancel-order-other@example.com",
            full_name="Pembeli Lain",
        )

        self.address = UserAddress.objects.create(
            user=self.user,
            label="Rumah",
            recipient_name="Penerima Uji",
            recipient_phone="081234567890",
            street_address="Jalan Contoh No. 1",
            subdistrict="Kaliwates",
            city="Jember",
            province="Jawa Timur",
            postal_code="68111",
        )

        category = Category.objects.create(name="Kategori Pembatalan")
        brand = Brand.objects.create(name="Brand Pembatalan")

        product = Product.objects.create(
            category=category,
            brand=brand,
            name="Produk Pembatalan",
            price=Decimal("100000.00"),
        )

        self.variant = ProductVariant.objects.create(
            product=product,
            color_name="Hitam",
            stock=10,
            sku="CANCEL-HITAM-001",
        )
        self.second_variant = ProductVariant.objects.create(
            product=product,
            color_name="Putih",
            stock=5,
            sku="CANCEL-PUTIH-001",
        )

        Cart.objects.create(
            user=self.user,
            product_variant=self.variant,
            quantity=2,
        )
        Cart.objects.create(
            user=self.user,
            product_variant=self.second_variant,
            quantity=1,
        )
        Cart.objects.create(
            user=self.other_user,
            product_variant=self.variant,
            quantity=1,
        )

        self.shipping = ShippingMethod.objects.create(
            name="Reguler",
            estimated_days="2-4 hari",
            base_cost=Decimal("15000.00"),
        )
        self.method = PaymentMethod.objects.create(
            name="Transfer Bank",
            channel_provider="Manual",
            service_fee=Decimal("2500.00"),
        )

        self.order, created = checkout_cart(
            user=self.user,
            checkout_key=uuid4(),
            address_id=self.address.pk,
            shipping_method_id=self.shipping.pk,
            payment_method_id=self.method.pk,
        )

        self.assertTrue(created)
        self.payment = self.order.payments.get()

    def _cancel(self, **changes):
        data = {
            "user": self.user,
            "order_id": self.order.pk,
        }
        data.update(changes)
        return cancel_order(**data)

    def _assert_not_cancelled(
        self,
        *,
        status=Order.Status.TO_PAY,
        stock=8,
        second_stock=4,
        payment_status=Payment.Status.PENDING,
    ):
        self.order.refresh_from_db()
        self.variant.refresh_from_db()
        self.second_variant.refresh_from_db()
        self.payment.refresh_from_db()

        self.assertEqual(self.order.status, status)
        self.assertTrue(self.order.stock_deducted)
        self.assertEqual(self.variant.stock, stock)
        self.assertEqual(self.second_variant.stock, second_stock)
        self.assertEqual(self.payment.payment_status, payment_status)

        self.assertEqual(
            self.order.trackings.filter(
                status_code=OrderTracking.StatusCode.CANCELLED,
            ).count(),
            0,
        )

    def test_unpaid_order_can_be_cancelled(self):
        result = self._cancel()

        self.assertEqual(result.pk, self.order.pk)

        self.order.refresh_from_db()
        self.variant.refresh_from_db()
        self.second_variant.refresh_from_db()
        self.payment.refresh_from_db()

        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertFalse(self.order.stock_deducted)
        self.assertEqual(self.variant.stock, 10)
        self.assertEqual(self.second_variant.stock, 5)
        self.assertEqual(
            self.payment.payment_status,
            Payment.Status.CANCELLED,
        )

        tracking = self.order.trackings.get(
            status_code=OrderTracking.StatusCode.CANCELLED,
        )
        self.assertTrue(tracking.is_completed)
        self.assertIsNotNone(tracking.event_time)

        self.assertEqual(self.order.items.count(), 2)
        self.assertFalse(Cart.objects.filter(user=self.user).exists())
        self.assertEqual(
            Cart.objects.get(user=self.other_user).quantity,
            1,
        )

        # Pesanan yang dibatalkan tidak bisa membuat pembayaran baru.
        with self.assertRaises(ValidationError):
            create_payment_transaction(
                user=self.user,
                order_id=self.order.pk,
                payment_method_id=self.method.pk,
            )

        self.assertEqual(self.order.payments.count(), 1)

    def test_login_is_required(self):
        with self.assertRaises(ValidationError):
            self._cancel(user=AnonymousUser())

        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            self._cancel()

        self._assert_not_cancelled()

    def test_other_user_cannot_cancel(self):
        with self.assertRaisesMessage(
            ValidationError,
            "Pesanan tidak ditemukan.",
        ):
            self._cancel(user=self.other_user)

        self._assert_not_cancelled()

    def test_missing_order_is_rejected(self):
        with self.assertRaisesMessage(
            ValidationError,
            "Pesanan tidak ditemukan.",
        ):
            self._cancel(order_id=self.order.pk + 10000)

        self._assert_not_cancelled()

    def test_invalid_order_ids_are_rejected(self):
        for order_id in (True, False, 0, -1, "1", None, 2**63):
            with self.subTest(order_id=order_id):
                with self.assertRaises(ValidationError):
                    self._cancel(order_id=order_id)

                self._assert_not_cancelled()

    def test_other_statuses_are_rejected(self):
        statuses = (
            Order.Status.PROCESSING,
            Order.Status.SHIPPED,
            Order.Status.COMPLETED,
        )

        for status in statuses:
            with self.subTest(status=status):
                Order.objects.filter(pk=self.order.pk).update(
                    status=status,
                )

                with self.assertRaises(ValidationError):
                    self._cancel()

                self._assert_not_cancelled(status=status)

    def test_any_successful_payment_blocks_cancellation(self):
        self.payment.payment_status = Payment.Status.SUCCESS
        self.payment.payment_amount = Decimal("1.00")
        self.payment.paid_at = timezone.now()
        self.payment.save(
            update_fields=[
                "payment_status",
                "payment_amount",
                "paid_at",
            ]
        )

        with self.assertRaises(ValidationError):
            self._cancel()

        self._assert_not_cancelled(
            payment_status=Payment.Status.SUCCESS,
        )

    def test_repeated_cancellation_does_not_restore_stock_twice(self):
        first = self._cancel()
        second = self._cancel()

        self.assertEqual(first.pk, second.pk)

        self.variant.refresh_from_db()
        self.second_variant.refresh_from_db()

        self.assertEqual(self.variant.stock, 10)
        self.assertEqual(self.second_variant.stock, 5)

        self.assertEqual(
            self.order.trackings.filter(
                status_code=OrderTracking.StatusCode.CANCELLED,
            ).count(),
            1,
        )
        self.assertEqual(self.order.payments.count(), 1)

    def test_current_stock_is_increased(self):
        # Simulasikan penambahan stok setelah checkout.
        self.variant.stock = 12
        self.variant.save(update_fields=["stock"])

        self._cancel()

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 14)

    def test_unreserved_stock_is_not_restored(self):
        # Simulasikan pesanan lama yang belum memotong stok.
        self.order.stock_deducted = False
        self.order.save(update_fields=["stock_deducted"])

        self.variant.stock = 10
        self.variant.save(update_fields=["stock"])

        self.second_variant.stock = 5
        self.second_variant.save(update_fields=["stock"])

        self._cancel()

        self.order.refresh_from_db()
        self.variant.refresh_from_db()
        self.second_variant.refresh_from_db()

        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertFalse(self.order.stock_deducted)
        self.assertEqual(self.variant.stock, 10)
        self.assertEqual(self.second_variant.stock, 5)

    def test_deleted_variant_does_not_break_cancellation(self):
        self.variant.delete()

        self._cancel()

        self.order.refresh_from_db()
        self.second_variant.refresh_from_db()

        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertFalse(self.order.stock_deducted)
        self.assertEqual(self.second_variant.stock, 5)
        self.assertEqual(self.order.items.count(), 2)

        deleted_item = self.order.items.get(
            product_variant__isnull=True,
        )
        self.assertEqual(deleted_item.sku_snapshot, "CANCEL-HITAM-001")
        self.assertEqual(deleted_item.quantity, 2)

    def test_only_pending_payments_are_cancelled(self):
        previous_attempts = []

        for status in (
            Payment.Status.PENDING,
            Payment.Status.FAILED,
            Payment.Status.EXPIRED,
        ):
            payment = Payment.objects.create(
                order=self.order,
                payment_method=self.method,
                payment_reference=f"ATTEMPT-{uuid4().hex}",
                payment_amount=self.order.total_amount,
                payment_status=status,
                expires_at=self.order.payment_due_at,
            )
            previous_attempts.append((payment, status))

        self._cancel()

        self.payment.refresh_from_db()
        self.assertEqual(
            self.payment.payment_status,
            Payment.Status.CANCELLED,
        )

        for payment, old_status in previous_attempts:
            payment.refresh_from_db()

            expected_status = (
                Payment.Status.CANCELLED
                if old_status == Payment.Status.PENDING
                else old_status
            )
            self.assertEqual(payment.payment_status, expected_status)

        self.assertEqual(self.order.payments.count(), 4)

    def test_missing_items_block_stock_restoration(self):
        self.order.items.all().delete()

        with self.assertRaisesMessage(
            ValidationError,
            "Data item pesanan tidak lengkap.",
        ):
            self._cancel()

        self._assert_not_cancelled()

    def test_stock_overflow_rolls_back_all_restorations(self):
        self.second_variant.stock = 2_147_483_647
        self.second_variant.save(update_fields=["stock"])

        with self.assertRaises(ValidationError):
            self._cancel()

        # Pengembalian stok varian pertama ikut dibatalkan.
        self._assert_not_cancelled(
            second_stock=2_147_483_647,
        )

    def test_tracking_failure_rolls_back_everything(self):
        with patch(
            "transactions.services.OrderTracking.objects.create",
            side_effect=RuntimeError("Pencatatan pembatalan gagal."),
        ):
            with self.assertRaisesMessage(
                RuntimeError,
                "Pencatatan pembatalan gagal.",
            ):
                self._cancel()

        self._assert_not_cancelled()
        self.assertEqual(self.order.trackings.count(), 1)
        self.assertEqual(self.order.items.count(), 2)

class OrderCancellationViewTests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            email="cancel-http@example.com",
            full_name="Pembeli Pembatalan HTTP",
        )
        self.other_user = User.objects.create_user(
            email="cancel-http-other@example.com",
            full_name="Pembeli Lain",
        )

        address = UserAddress.objects.create(
            user=self.user,
            label="Rumah",
            recipient_name="Penerima Uji",
            recipient_phone="081234567890",
            street_address="Jalan Contoh No. 1",
            subdistrict="Kaliwates",
            city="Jember",
            province="Jawa Timur",
            postal_code="68111",
        )

        category = Category.objects.create(
            name="Kategori Pembatalan HTTP",
        )
        brand = Brand.objects.create(
            name="Brand Pembatalan HTTP",
        )
        product = Product.objects.create(
            category=category,
            brand=brand,
            name="Produk Pembatalan HTTP",
            price=Decimal("100000.00"),
        )

        self.variant = ProductVariant.objects.create(
            product=product,
            color_name="Hitam",
            stock=10,
            sku="CANCEL-HTTP-HITAM-001",
        )

        Cart.objects.create(
            user=self.user,
            product_variant=self.variant,
            quantity=2,
        )
        Cart.objects.create(
            user=self.other_user,
            product_variant=self.variant,
            quantity=1,
        )

        shipping = ShippingMethod.objects.create(
            name="Reguler",
            estimated_days="2-4 hari",
            base_cost=Decimal("15000.00"),
        )
        method = PaymentMethod.objects.create(
            name="Transfer Bank",
            channel_provider="Manual",
            service_fee=Decimal("2500.00"),
        )

        self.order, created = checkout_cart(
            user=self.user,
            checkout_key=uuid4(),
            address_id=address.pk,
            shipping_method_id=shipping.pk,
            payment_method_id=method.pk,
        )

        self.assertTrue(created)
        self.payment = self.order.payments.get()
        self.url = f"/api/orders/{self.order.pk}/cancel/"

        self.client.force_login(self.user)

    def _assert_unchanged(
        self,
        *,
        status=Order.Status.TO_PAY,
        payment_status=Payment.Status.PENDING,
    ):
        self.order.refresh_from_db()
        self.variant.refresh_from_db()
        self.payment.refresh_from_db()

        self.assertEqual(self.order.status, status)
        self.assertTrue(self.order.stock_deducted)
        self.assertEqual(self.variant.stock, 8)
        self.assertEqual(
            self.payment.payment_status,
            payment_status,
        )
        self.assertEqual(self.order.payments.count(), 1)
        self.assertEqual(self.order.trackings.count(), 1)

        self.assertFalse(
            self.order.trackings.filter(
                status_code=OrderTracking.StatusCode.CANCELLED,
            ).exists()
        )

        self.assertEqual(
            Cart.objects.get(user=self.other_user).quantity,
            1,
        )

    def _assert_cancelled(self):
        self.order.refresh_from_db()
        self.variant.refresh_from_db()
        self.payment.refresh_from_db()

        self.assertEqual(
            self.order.status,
            Order.Status.CANCELLED,
        )
        self.assertFalse(self.order.stock_deducted)
        self.assertEqual(self.variant.stock, 10)
        self.assertEqual(
            self.payment.payment_status,
            Payment.Status.CANCELLED,
        )

        self.assertEqual(self.order.payments.count(), 1)
        self.assertEqual(self.order.items.count(), 1)
        self.assertEqual(self.order.trackings.count(), 2)

        self.assertEqual(
            self.order.trackings.filter(
                status_code=OrderTracking.StatusCode.CANCELLED,
            ).count(),
            1,
        )

        self.assertFalse(
            Cart.objects.filter(user=self.user).exists()
        )
        self.assertEqual(
            Cart.objects.get(user=self.other_user).quantity,
            1,
        )

    def test_owner_can_cancel(self):
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["data"],
            {
                "id": self.order.pk,
                "order_number": self.order.order_number,
                "status": Order.Status.CANCELLED,
            },
        )

        self._assert_cancelled()

    def test_login_is_required(self):
        self.client.logout()

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 401)
        self.assertIn("message", response.json())
        self._assert_unchanged()

    def test_other_user_cannot_cancel(self):
        self.client.force_login(self.other_user)

        response = self.client.post(
            self.url,
            data={
                "user_id": self.user.pk,
                "status": Order.Status.CANCELLED,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["message"],
            "Pesanan tidak ditemukan.",
        )
        self._assert_unchanged()

    def test_missing_or_invalid_order_returns_404(self):
        for order_id in (0, self.order.pk + 10000, 2**63):
            with self.subTest(order_id=order_id):
                response = self.client.post(
                    f"/api/orders/{order_id}/cancel/",
                )

                self.assertEqual(response.status_code, 404)
                self.assertIn("message", response.json())
                self._assert_unchanged()

    def test_get_is_rejected_without_changes(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)
        self._assert_unchanged()

    def test_invalid_status_or_successful_payment_is_rejected(self):
        for status in (
            Order.Status.PROCESSING,
            Order.Status.SHIPPED,
            Order.Status.COMPLETED,
        ):
            with self.subTest(status=status):
                Order.objects.filter(pk=self.order.pk).update(
                    status=status,
                )

                response = self.client.post(self.url)

                self.assertEqual(response.status_code, 400)
                self.assertIn("message", response.json())
                self._assert_unchanged(status=status)

        Order.objects.filter(pk=self.order.pk).update(
            status=Order.Status.TO_PAY,
        )

        self.payment.payment_status = Payment.Status.SUCCESS
        self.payment.paid_at = timezone.now()
        self.payment.save(
            update_fields=["payment_status", "paid_at"],
        )

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 400)
        self.assertIn("message", response.json())
        self._assert_unchanged(
            payment_status=Payment.Status.SUCCESS,
        )

    def test_repeated_cancellation_does_not_duplicate_changes(self):
        first = self.client.post(self.url)
        second = self.client.post(self.url)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            first.json()["data"],
            second.json()["data"],
        )

        self.assertEqual(Order.objects.count(), 1)
        self._assert_cancelled()

    def test_csrf_is_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        rejected = client.post(self.url)

        self.assertEqual(rejected.status_code, 403)
        self._assert_unchanged()

        # Nilai tetap ini hanya digunakan untuk tes.
        csrf_token = "a" * 32
        client.cookies[settings.CSRF_COOKIE_NAME] = csrf_token

        accepted = client.post(
            self.url,
            headers={"X-CSRFToken": csrf_token},
        )

        self.assertEqual(accepted.status_code, 200)
        self._assert_cancelled()

class ExpirationTestMixin:
    def setUp(self):
        super().setUp()

        self.check_time = timezone.now()

        self.user = get_user_model().objects.create_user(
            email="expiration@example.com",
            full_name="Pembeli Kedaluwarsa",
        )

        self.address = UserAddress.objects.create(
            user=self.user,
            label="Rumah",
            recipient_name="Penerima Uji",
            recipient_phone="081234567890",
            street_address="Jalan Contoh No. 1",
            subdistrict="Kaliwates",
            city="Jember",
            province="Jawa Timur",
            postal_code="68111",
        )

        category = Category.objects.create(name="Kategori Kedaluwarsa")
        brand = Brand.objects.create(name="Brand Kedaluwarsa")

        product = Product.objects.create(
            category=category,
            brand=brand,
            name="Produk Kedaluwarsa",
            price=Decimal("100000.00"),
        )

        self.variant = ProductVariant.objects.create(
            product=product,
            color_name="Hitam",
            stock=10,
            sku="EXPIRATION-HITAM-001",
        )

        self.shipping = ShippingMethod.objects.create(
            name="Reguler",
            estimated_days="2-4 hari",
            base_cost=Decimal("15000.00"),
        )
        self.method = PaymentMethod.objects.create(
            name="Transfer Bank",
            channel_provider="Manual",
            service_fee=Decimal("2500.00"),
        )

        self.order = self._make_order()
        self.payment = self.order.payments.get()

    def _make_order(self, *, minutes_until_due=-1):
        Cart.objects.create(
            user=self.user,
            product_variant=self.variant,
            quantity=2,
        )

        order, created = checkout_cart(
            user=self.user,
            checkout_key=uuid4(),
            address_id=self.address.pk,
            shipping_method_id=self.shipping.pk,
            payment_method_id=self.method.pk,
        )

        self.assertTrue(created)

        due_at = (
            None
            if minutes_until_due is None
            else self.check_time + timedelta(minutes=minutes_until_due)
        )

        order.payment_due_at = due_at
        order.save(update_fields=["payment_due_at"])
        order.payments.update(expires_at=due_at)

        return order

    def _assert_unchanged(
        self,
        *,
        stock=8,
        status=Order.Status.TO_PAY,
        payment_status=Payment.Status.PENDING,
    ):
        self.order.refresh_from_db()
        self.variant.refresh_from_db()
        self.payment.refresh_from_db()

        self.assertEqual(self.order.status, status)
        self.assertTrue(self.order.stock_deducted)
        self.assertEqual(self.variant.stock, stock)
        self.assertEqual(self.payment.payment_status, payment_status)
        self.assertEqual(self.order.trackings.count(), 1)

        self.assertFalse(
            self.order.trackings.filter(
                status_code=OrderTracking.StatusCode.CANCELLED,
            ).exists()
        )

    def _assert_expired(self, *, stock=10):
        self.order.refresh_from_db()
        self.variant.refresh_from_db()
        self.payment.refresh_from_db()

        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertFalse(self.order.stock_deducted)
        self.assertEqual(self.variant.stock, stock)
        self.assertEqual(
            self.payment.payment_status,
            Payment.Status.EXPIRED,
        )
        self.assertEqual(self.order.items.count(), 1)
        self.assertEqual(self.order.trackings.count(), 2)

        tracking = self.order.trackings.get(
            status_code=OrderTracking.StatusCode.CANCELLED,
        )
        self.assertTrue(tracking.is_completed)
        self.assertIsNotNone(tracking.event_time)
        self.assertIn("batas waktu pembayaran", tracking.description)


class OrderExpirationServiceTests(ExpirationTestMixin, TestCase):
    def test_overdue_order_is_expired_and_stock_is_restored(self):
        changed = expire_unpaid_order(order_id=self.order.pk)

        self.assertTrue(changed)
        self._assert_expired()

    def test_future_or_missing_deadline_is_ignored(self):
        deadlines = (
            self.check_time + timedelta(hours=1),
            None,
        )

        for deadline in deadlines:
            with self.subTest(deadline=deadline):
                self.order.payment_due_at = deadline
                self.order.save(update_fields=["payment_due_at"])
                self.order.payments.update(expires_at=deadline)

                changed = expire_unpaid_order(order_id=self.order.pk)

                self.assertFalse(changed)
                self._assert_unchanged()

    def test_exact_deadline_is_expired(self):
        self.order.payment_due_at = self.check_time
        self.order.save(update_fields=["payment_due_at"])
        self.order.payments.update(expires_at=self.check_time)

        with patch(
            "transactions.services.timezone.now",
            return_value=self.check_time,
        ):
            changed = expire_unpaid_order(order_id=self.order.pk)

        self.assertTrue(changed)
        self._assert_expired()

    def test_other_order_statuses_are_ignored(self):
        for status in (
            Order.Status.PROCESSING,
            Order.Status.SHIPPED,
            Order.Status.COMPLETED,
        ):
            with self.subTest(status=status):
                Order.objects.filter(pk=self.order.pk).update(
                    status=status,
                )

                changed = expire_unpaid_order(order_id=self.order.pk)

                self.assertFalse(changed)
                self._assert_unchanged(status=status)

    def test_successful_payment_blocks_expiration(self):
        self.payment.payment_status = Payment.Status.SUCCESS
        self.payment.payment_amount = Decimal("1.00")
        self.payment.paid_at = self.check_time
        self.payment.save(
            update_fields=[
                "payment_status",
                "payment_amount",
                "paid_at",
            ]
        )

        changed = expire_unpaid_order(order_id=self.order.pk)

        self.assertFalse(changed)
        self._assert_unchanged(
            payment_status=Payment.Status.SUCCESS,
        )

    def test_repeated_expiration_does_not_duplicate_changes(self):
        first = expire_unpaid_order(order_id=self.order.pk)
        second = expire_unpaid_order(order_id=self.order.pk)

        self.assertTrue(first)
        self.assertFalse(second)
        self._assert_expired()

    def test_manual_cancellation_prevents_expiration(self):
        cancel_order(user=self.user, order_id=self.order.pk)

        changed = expire_unpaid_order(order_id=self.order.pk)

        self.assertFalse(changed)

        self.order.refresh_from_db()
        self.variant.refresh_from_db()
        self.payment.refresh_from_db()

        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertFalse(self.order.stock_deducted)
        self.assertEqual(self.variant.stock, 10)
        self.assertEqual(
            self.payment.payment_status,
            Payment.Status.CANCELLED,
        )
        self.assertEqual(self.order.trackings.count(), 2)

    def test_expiration_then_manual_cancellation_keeps_expired_payment(self):
        self.assertTrue(
            expire_unpaid_order(order_id=self.order.pk)
        )

        result = cancel_order(
            user=self.user,
            order_id=self.order.pk,
        )

        self.assertEqual(result.pk, self.order.pk)
        self._assert_expired()

    def test_inactive_users_orders_can_still_expire(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        changed = expire_unpaid_order(order_id=self.order.pk)

        self.assertTrue(changed)
        self._assert_expired()

    def test_tracking_failure_rolls_back_everything(self):
        with patch(
            "transactions.services.OrderTracking.objects.create",
            side_effect=RuntimeError("Pencatatan kedaluwarsa gagal."),
        ):
            with self.assertRaisesMessage(
                RuntimeError,
                "Pencatatan kedaluwarsa gagal.",
            ):
                expire_unpaid_order(order_id=self.order.pk)

        self._assert_unchanged()

    def test_missing_order_is_ignored(self):
        changed = expire_unpaid_order(
            order_id=self.order.pk + 10000,
        )

        self.assertFalse(changed)
        self._assert_unchanged()

    def test_unreserved_stock_is_not_restored(self):
        self.order.stock_deducted = False
        self.order.save(update_fields=["stock_deducted"])

        self.variant.stock = 10
        self.variant.save(update_fields=["stock"])

        changed = expire_unpaid_order(order_id=self.order.pk)

        self.assertTrue(changed)
        self._assert_expired(stock=10)


class ExpireOrdersCommandTests(ExpirationTestMixin, TestCase):
    def test_command_processes_only_eligible_orders(self):
        future_order = self._make_order(minutes_until_due=60)
        paid_order = self._make_order()

        paid_order.payments.update(
            payment_status=Payment.Status.SUCCESS,
            paid_at=self.check_time,
        )

        output = StringIO()

        call_command(
            "expire_orders",
            stdout=output,
            stderr=StringIO(),
        )

        # Tiga pesanan memotong stok menjadi 4.
        # Hanya satu pesanan kedaluwarsa, sehingga stok menjadi 6.
        self._assert_expired(stock=6)

        future_order.refresh_from_db()
        paid_order.refresh_from_db()

        self.assertEqual(future_order.status, Order.Status.TO_PAY)
        self.assertEqual(
            future_order.payments.get().payment_status,
            Payment.Status.PENDING,
        )
        self.assertEqual(paid_order.status, Order.Status.TO_PAY)
        self.assertEqual(
            paid_order.payments.get().payment_status,
            Payment.Status.SUCCESS,
        )

        self.assertIn(
            "Kedaluwarsa: 1; dilewati: 1; gagal: 0.",
            output.getvalue(),
        )

    def test_batching_and_repeated_runs_do_not_duplicate_changes(self):
        self._make_order()
        self._make_order()

        first_output = StringIO()

        call_command(
            "expire_orders",
            batch_size=1,
            stdout=first_output,
            stderr=StringIO(),
        )

        self.assertIn(
            "Kedaluwarsa: 3; dilewati: 0; gagal: 0.",
            first_output.getvalue(),
        )
        self._assert_expired()

        second_output = StringIO()

        call_command(
            "expire_orders",
            batch_size=1,
            stdout=second_output,
            stderr=StringIO(),
        )

        self.assertIn(
            "Kedaluwarsa: 0; dilewati: 0; gagal: 0.",
            second_output.getvalue(),
        )
        self._assert_expired()

        self.assertEqual(
            Order.objects.filter(
                status=Order.Status.CANCELLED,
            ).count(),
            3,
        )
        self.assertEqual(
            OrderTracking.objects.filter(
                status_code=OrderTracking.StatusCode.CANCELLED,
            ).count(),
            3,
        )

    def test_invalid_batch_size_is_rejected(self):
        for batch_size in (0, -1, 1001, True):
            with self.subTest(batch_size=batch_size):
                with self.assertRaises(CommandError):
                    call_command(
                        "expire_orders",
                        batch_size=batch_size,
                        stdout=StringIO(),
                        stderr=StringIO(),
                    )

                self._assert_unchanged()

    def test_one_invalid_order_does_not_block_later_orders(self):
        healthy_order = self._make_order()

        # Simulasikan data pesanan pertama yang tidak lengkap.
        self.order.items.all().delete()

        output = StringIO()
        errors = StringIO()

        with self.assertRaises(CommandError):
            call_command(
                "expire_orders",
                batch_size=1,
                stdout=output,
                stderr=errors,
            )

        # Stok pesanan bermasalah tetap tertahan.
        # Stok pesanan sehat berhasil dikembalikan.
        self._assert_unchanged(stock=8)

        healthy_order.refresh_from_db()

        self.assertEqual(
            healthy_order.status,
            Order.Status.CANCELLED,
        )
        self.assertFalse(healthy_order.stock_deducted)
        self.assertEqual(
            healthy_order.payments.get().payment_status,
            Payment.Status.EXPIRED,
        )

        self.assertIn(
            "Kedaluwarsa: 1; dilewati: 0; gagal: 1.",
            output.getvalue(),
        )
        self.assertIn(
            f"Pesanan {self.order.pk}:",
            errors.getvalue(),
        )

class TransactionIntegrationTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.password = "Pasaryo-Integrasi-2026!Aman"
        self.checkout_key = str(uuid4())

        self.user = get_user_model().objects.create_user(
            email="integration-flow@example.com",
            full_name="Pembeli Integrasi",
            password=self.password,
        )

        self.address = UserAddress.objects.create(
            user=self.user,
            label="Rumah",
            recipient_name="Penerima Integrasi",
            recipient_phone="081234567890",
            street_address="Jalan Contoh No. 1",
            subdistrict="Kaliwates",
            city="Jember",
            province="Jawa Timur",
            postal_code="68111",
        )

        category = Category.objects.create(name="Kategori Integrasi")
        brand = Brand.objects.create(name="Brand Integrasi")

        self.product = Product.objects.create(
            category=category,
            brand=brand,
            name="Produk Integrasi",
            price=Decimal("100000.00"),
        )

        self.variant = ProductVariant.objects.create(
            product=self.product,
            color_name="Hitam",
            stock=10,
            sku="INTEGRATION-HITAM-001",
        )

        self.shipping = ShippingMethod.objects.create(
            name="Reguler",
            estimated_days="2-4 hari",
            base_cost=Decimal("15000.00"),
        )

        self.method = PaymentMethod.objects.create(
            name="Transfer Bank",
            channel_provider="Manual",
            service_fee=Decimal("2500.00"),
        )

        self.promo = PromoCode.objects.create(
            code="INTEGRASI10",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("10.00"),
            max_discount=Decimal("50000.00"),
            min_order_amount=Decimal("100000.00"),
            quota_total=100,
            quota_per_user=1,
            expires_at=timezone.now() + timedelta(days=7),
            is_active=True,
        )

    def _get_json(self, path, *, client=None, expected_status=200):
        client = self.client if client is None else client
        response = client.get(path)

        self.assertEqual(
            response.status_code,
            expected_status,
            response.content.decode("utf-8", errors="replace"),
        )

        return response.json()

    def _post_json(
        self,
        path,
        payload,
        csrf_token,
        *,
        client=None,
        expected_status=200,
    ):
        client = self.client if client is None else client

        response = client.post(
            path,
            data=payload,
            content_type="application/json",
            headers={"X-CSRFToken": csrf_token},
        )

        self.assertEqual(
            response.status_code,
            expected_status,
            response.content.decode("utf-8", errors="replace"),
        )

        return response.json()

    def _login(self, *, client=None, user=None):
        client = self.client if client is None else client
        user = self.user if user is None else user

        initial_token = self._get_json(
            "/accounts/csrf/",
            client=client,
        )["csrf_token"]

        result = self._post_json(
            "/accounts/login/",
            {
                "email": user.email,
                "password": self.password,
            },
            initial_token,
            client=client,
        )

        self.assertEqual(result["user"]["id"], user.pk)
        self.assertIn(settings.SESSION_COOKIE_NAME, client.cookies)

        current_user = self._get_json(
            "/accounts/me/",
            client=client,
        )["user"]

        self.assertEqual(current_user["id"], user.pk)

        return result["csrf_token"]

    def _add_to_cart(self, csrf_token, *, quantity=2):
        return self._post_json(
            "/api/cart/",
            {
                "product_variant_id": self.variant.pk,
                "quantity": quantity,
            },
            csrf_token,
            expected_status=201,
        )["data"]

    def _checkout(
        self,
        csrf_token,
        *,
        promo_code=None,
        expected_status=201,
    ):
        payload = {
            "checkout_key": self.checkout_key,
            "address_id": self.address.pk,
            "shipping_method_id": self.shipping.pk,
            "payment_method_id": self.method.pk,
        }

        if promo_code is not None:
            payload["promo_code"] = promo_code

        return self._post_json(
            "/api/checkout/",
            payload,
            csrf_token,
            expected_status=expected_status,
        )["data"]

    def test_login_cart_promo_checkout_history_and_cancellation(self):
        other_user = get_user_model().objects.create_user(
            email="integration-other@example.com",
            full_name="Pembeli Lain",
            password=self.password,
        )

        Cart.objects.create(
            user=other_user,
            product_variant=self.variant,
            quantity=1,
        )

        token = self._login()

        shipping_methods = self._get_json(
            "/api/shipping-methods/",
        )["data"]
        payment_methods = self._get_json(
            "/api/payment-methods/",
        )["data"]

        self.assertIn(
            self.shipping.pk,
            [row["id"] for row in shipping_methods],
        )
        self.assertIn(
            self.method.pk,
            [row["id"] for row in payment_methods],
        )

        cart = self._add_to_cart(token)

        self.assertEqual(cart["subtotal"], "200000.00")
        self.assertEqual(cart["total_quantity"], 2)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 10)

        preview = self._post_json(
            "/api/promo-codes/validate/",
            {"code": self.promo.code},
            token,
        )["data"]

        self.assertEqual(preview["subtotal"], "200000.00")
        self.assertEqual(preview["discount_amount"], "20000.00")

        checkout = self._checkout(
            token,
            promo_code=self.promo.code,
        )
        order_id = checkout["id"]

        self.assertEqual(checkout["subtotal"], "200000.00")
        self.assertEqual(checkout["discount_amount"], "20000.00")
        self.assertEqual(checkout["total_amount"], "197500.00")
        self.assertEqual(
            checkout["payment"]["payment_status"],
            Payment.Status.PENDING,
        )

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 8)

        empty_cart = self._get_json("/api/cart/")["data"]
        self.assertEqual(empty_cart["items"], [])

        # Perubahan katalog setelah pembelian.
        self.product.name = "Produk Setelah Pembelian"
        self.product.price = Decimal("125000.00")
        self.product.save(update_fields=["name", "price"])

        # Pengiriman ulang checkout mengembalikan pesanan sebelumnya.
        retry = self._checkout(
            token,
            promo_code=self.promo.code,
            expected_status=200,
        )

        self.assertEqual(retry["id"], order_id)
        self.assertEqual(retry["total_amount"], "197500.00")
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)

        history = self._get_json("/api/orders/")["data"]
        detail = self._get_json(
            f"/api/orders/{order_id}/",
        )["data"]

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["id"], order_id)
        self.assertEqual(detail["total_amount"], "197500.00")
        self.assertEqual(
            detail["items"][0]["product_name"],
            "Produk Integrasi",
        )
        self.assertEqual(
            detail["items"][0]["unit_price"],
            "100000.00",
        )

        self._get_json(f"/api/orders/{order_id}/tracking/")

        # Login pengguna kedua melalui endpoint auth yang sama.
        other_client = Client(enforce_csrf_checks=True)
        other_token = self._login(
            client=other_client,
            user=other_user,
        )

        other_history = self._get_json(
            "/api/orders/",
            client=other_client,
        )["data"]
        self.assertEqual(other_history, [])

        self.assertEqual(
            other_client.get(
                f"/api/orders/{order_id}/",
            ).status_code,
            404,
        )
        self.assertEqual(
            other_client.get(
                f"/api/orders/{order_id}/tracking/",
            ).status_code,
            404,
        )

        self._post_json(
            f"/api/orders/{order_id}/cancel/",
            {},
            other_token,
            client=other_client,
            expected_status=404,
        )

        cancelled = self._post_json(
            f"/api/orders/{order_id}/cancel/",
            {},
            token,
        )["data"]

        self.assertEqual(
            cancelled["status"],
            Order.Status.CANCELLED,
        )

        detail = self._get_json(
            f"/api/orders/{order_id}/",
        )["data"]

        self.assertEqual(detail["status"], Order.Status.CANCELLED)
        self.assertEqual(
            detail["payment"]["payment_status"],
            Payment.Status.CANCELLED,
        )

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 10)
        self.assertEqual(
            Cart.objects.get(user=other_user).quantity,
            1,
        )

    def test_checkout_then_expiration_updates_order_history(self):
        token = self._login()
        self._add_to_cart(token)

        checkout = self._checkout(token)
        order_id = checkout["id"]
        order = Order.objects.get(pk=order_id)

        # Simulasi waktu pembayaran habis pada database tes.
        deadline = timezone.now() - timedelta(minutes=1)
        order.payment_due_at = deadline
        order.save(update_fields=["payment_due_at"])
        order.payments.update(expires_at=deadline)

        # Pembayaran baru ditolak meskipun command belum dijalankan.
        self._post_json(
            f"/api/orders/{order_id}/payments/",
            {"payment_method_id": self.method.pk},
            token,
            expected_status=400,
        )

        output = StringIO()

        call_command(
            "expire_orders",
            stdout=output,
            stderr=StringIO(),
        )

        self.assertIn("Kedaluwarsa: 1;", output.getvalue())

        detail = self._get_json(
            f"/api/orders/{order_id}/",
        )["data"]
        history = self._get_json("/api/orders/")["data"]

        self.assertEqual(detail["status"], Order.Status.CANCELLED)
        self.assertEqual(
            detail["payment"]["payment_status"],
            Payment.Status.EXPIRED,
        )
        self.assertEqual(
            detail["payment"]["payment_reference"],
            checkout["payment"]["payment_reference"],
        )
        self.assertEqual(
            history[0]["status"],
            Order.Status.CANCELLED,
        )

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 10)
        self.assertEqual(order.payments.count(), 1)

    def test_paid_and_shipped_order_can_be_received(self):
        token = self._login()
        self._add_to_cart(token)

        checkout = self._checkout(token)
        order_id = checkout["id"]
        event_time = timezone.now()

        # Data tes yang mewakili konfirmasi pembayaran oleh admin.
        Payment.objects.filter(order_id=order_id).update(
            payment_status=Payment.Status.SUCCESS,
            paid_at=event_time,
        )

        # Data tes yang mewakili proses pengiriman oleh admin.
        Order.objects.filter(pk=order_id).update(
            status=Order.Status.SHIPPED,
        )
        OrderTracking.objects.create(
            order_id=order_id,
            status_code=OrderTracking.StatusCode.SHIPPED,
            description="Simulasi pengiriman oleh admin pada tes.",
            event_time=event_time,
            is_completed=True,
        )

        completed = self._post_json(
            f"/api/orders/{order_id}/complete/",
            {},
            token,
        )["data"]

        repeated = self._post_json(
            f"/api/orders/{order_id}/complete/",
            {},
            token,
        )["data"]

        self.assertEqual(
            completed["status"],
            Order.Status.COMPLETED,
        )
        self.assertEqual(completed, repeated)

        detail = self._get_json(
            f"/api/orders/{order_id}/",
        )["data"]

        self.assertEqual(detail["status"], Order.Status.COMPLETED)
        self.assertEqual(
            detail["payment"]["payment_status"],
            Payment.Status.SUCCESS,
        )
        self.assertEqual(
            OrderTracking.objects.filter(
                order_id=order_id,
                status_code=OrderTracking.StatusCode.DELIVERED,
            ).count(),
            1,
        )

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 8)

    def test_login_rotates_csrf_token_for_transaction_requests(self):
        credentials = {
            "email": self.user.email,
            "password": self.password,
        }

        # Endpoint login juga harus dilindungi CSRF.
        missing_token = self.client.post(
            "/accounts/login/",
            data=credentials,
            content_type="application/json",
        )
        self.assertEqual(missing_token.status_code, 403)

        old_token = self._get_json(
            "/accounts/csrf/",
        )["csrf_token"]

        login_result = self._post_json(
            "/accounts/login/",
            credentials,
            old_token,
        )
        new_token = login_result["csrf_token"]

        rejected = self.client.post(
            "/api/cart/",
            data={
                "product_variant_id": self.variant.pk,
                "quantity": 2,
            },
            content_type="application/json",
            headers={"X-CSRFToken": old_token},
        )

        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(Cart.objects.count(), 0)

        cart = self._add_to_cart(new_token)
        self.assertEqual(cart["total_quantity"], 2)

    def test_invalid_login_and_logout_block_protected_apis(self):
        initial_token = self._get_json(
            "/accounts/csrf/",
        )["csrf_token"]

        self._post_json(
            "/accounts/login/",
            {
                "email": self.user.email,
                "password": "Password-Salah-Untuk-Tes!2026",
            },
            initial_token,
            expected_status=401,
        )

        self._get_json("/accounts/me/", expected_status=401)
        self._get_json("/api/cart/", expected_status=401)

        token = self._login()
        self._add_to_cart(token, quantity=1)

        self._post_json(
            "/accounts/logout/",
            {},
            token,
        )

        for path in (
            "/accounts/me/",
            "/api/cart/",
            "/api/orders/",
        ):
            with self.subTest(path=path):
                self._get_json(path, expected_status=401)

        # Logout mempertahankan isi keranjang milik akun.
        self.assertEqual(
            Cart.objects.get(user=self.user).quantity,
            1,
        )
        self.assertEqual(Order.objects.count(), 0)