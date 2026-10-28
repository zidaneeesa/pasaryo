from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.utils import timezone
from django.contrib.auth.models import AnonymousUser
from django.conf import settings

from .models import (
    DiscountType,
    Order,
    PromoCode,
    ShippingMethod,
)
from .models import OrderTracking
from .models import Payment, PaymentMethod
from .services import create_payment_transaction, validate_promo_code


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