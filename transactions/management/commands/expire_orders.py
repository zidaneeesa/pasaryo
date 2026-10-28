from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from transactions.models import Order
from transactions.services import expire_unpaid_order


class Command(BaseCommand):
    help = "Menutup pesanan yang melewati batas waktu pembayaran."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=200,
            help="Jumlah pesanan per pengambilan data, antara 1 dan 1000.",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]

        if type(batch_size) is not int or not 1 <= batch_size <= 1000:
            raise CommandError("batch-size harus antara 1 dan 1000.")

        cutoff = timezone.now()
        last_id = 0

        expired = 0
        skipped = 0
        failed = 0

        while True:
            order_ids = list(
                Order.objects.filter(
                    pk__gt=last_id,
                    status=Order.Status.TO_PAY,
                    payment_due_at__lte=cutoff,
                )
                .order_by("pk")
                .values_list("pk", flat=True)[:batch_size]
            )

            if not order_ids:
                break

            for order_id in order_ids:
                try:
                    changed = expire_unpaid_order(order_id=order_id)
                except ValidationError as exc:
                    failed += 1
                    self.stderr.write(
                        f"Pesanan {order_id}: {' '.join(exc.messages)}"
                    )
                else:
                    if changed:
                        expired += 1
                    else:
                        skipped += 1

            last_id = order_ids[-1]

        self.stdout.write(
            f"Kedaluwarsa: {expired}; "
            f"dilewati: {skipped}; "
            f"gagal: {failed}."
        )

        if failed:
            raise CommandError(
                "Sebagian pesanan gagal diproses. "
                "Periksa pesan error lalu jalankan ulang."
            )