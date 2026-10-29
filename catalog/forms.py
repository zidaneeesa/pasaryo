from django import forms


# Form validasi parameter filter, pencarian, pengurutan (sorting), dan paginasi katalog produk.
# Menggunakan Form biasa untuk memvalidasi query params URL (GET request) sebelum diproses ke query database.
class ProductFilterForm(forms.Form):
    q = forms.CharField(required=False, max_length=200)
    category_id = forms.IntegerField(required=False, min_value=1)
    brand_id = forms.IntegerField(required=False, min_value=1)

    min_price = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=12,
        decimal_places=2,
    )
    max_price = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=12,
        decimal_places=2,
    )

    origin_city = forms.CharField(required=False, max_length=100)

    sort = forms.ChoiceField(
        required=False,
        choices=[
            ("-id", "Terbaru"),
            ("price", "Harga termurah"),
            ("-price", "Harga termahal"),
            ("name", "Nama A-Z"),
        ],
    )

    page = forms.IntegerField(required=False, min_value=1)
    page_size = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=100,
    )

    # Validasi logika relasi antar-field (rentang harga):
    # Memastikan harga minimum tidak lebih besar dari harga maksimum agar query filter tidak menghasilkan error/kontradiksi.
    def clean(self):
        data = super().clean()
        minimum = data.get("min_price")
        maximum = data.get("max_price")

        if (
            minimum is not None
            and maximum is not None
            and minimum > maximum
        ):
            raise forms.ValidationError(
                "Harga minimum tidak boleh melebihi harga maksimum."
            )

        return data