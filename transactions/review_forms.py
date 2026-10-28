from django import forms

from .models import Review


class ReviewForm(forms.ModelForm):
    rating = forms.IntegerField(min_value=1, max_value=5)

    class Meta:
        model = Review
        fields = ["rating", "comment"]

    def clean_rating(self):
        if type(self.data.get("rating")) is not int:
            raise forms.ValidationError(
                "Rating harus berupa bilangan bulat."
            )
        return self.cleaned_data["rating"]

    def clean_comment(self):
        if not isinstance(self.data.get("comment", ""), str):
            raise forms.ValidationError(
                "Komentar harus berupa teks."
            )
        return self.cleaned_data["comment"]


class ReviewPageForm(forms.Form):
    page = forms.IntegerField(required=False, min_value=1)
    page_size = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=100,
    )