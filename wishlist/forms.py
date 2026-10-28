from django import forms


class WishlistPageForm(forms.Form):
    page = forms.IntegerField(required=False, min_value=1)
    page_size = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=100,
    )