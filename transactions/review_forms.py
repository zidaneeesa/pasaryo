from django import forms

from .models import Review


# Form validasi pengiriman ulasan (review) produk setelah pesanan selesai.
# Menggunakan ModelForm terikat ke model Review dengan batas rating 1 sampai 5 bintang.
class ReviewForm(forms.ModelForm):
    rating = forms.IntegerField(min_value=1, max_value=5)

    class Meta:
        model = Review
        fields = ["rating", "comment"]

    # Validasi tipe data rating:
    # Memastikan input berupa bilangan bulat (integer murni), bukan string angka desimal atau tipe lain.
    def clean_rating(self):
        if type(self.data.get("rating")) is not int:
            raise forms.ValidationError(
                "Rating harus berupa bilangan bulat."
            )
        return self.cleaned_data["rating"]

    # Validasi tipe data komentar ulasan:
    # Memastikan isi komentar berupa teks string yang sah.
    def clean_comment(self):
        if not isinstance(self.data.get("comment", ""), str):
            raise forms.ValidationError(
                "Komentar harus berupa teks."
            )
        return self.cleaned_data["comment"]


# Form validasi parameter paginasi untuk daftar ulasan produk.
# Mengatur batas aman nomor halaman (min 1) dan jumlah ulasan per halaman (1-100).
class ReviewPageForm(forms.Form):
    page = forms.IntegerField(required=False, min_value=1)
    page_size = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=100,
    )