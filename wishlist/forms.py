from django import forms


# Form validasi parameter paginasi untuk daftar wishlist pengguna.
# Memastikan nomor halaman (page) minimal 1 dan ukuran halaman (page_size) berada di batas wajar (1-100) demi performa server.
class WishlistPageForm(forms.Form):
    page = forms.IntegerField(required=False, min_value=1)
    page_size = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=100,
    )