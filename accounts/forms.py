from django import forms
from PIL import Image

from accounts.models import UserSignature

MAX_SIGNATURE_BYTES = 300 * 1024
MAX_SIGNATURE_WIDTH = 1000
MAX_SIGNATURE_HEIGHT = 400


class UserSignatureForm(forms.ModelForm):
    class Meta:
        model = UserSignature
        fields = ['image']

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if not image:
            return image

        if image.size > MAX_SIGNATURE_BYTES:
            raise forms.ValidationError(
                f"L'immagine supera la dimensione massima consentita "
                f"({MAX_SIGNATURE_BYTES // 1024} KB)."
            )

        try:
            probe = Image.open(image)
            probe.verify()
        except Exception:
            raise forms.ValidationError("Il file caricato non è un'immagine valida.")

        image.seek(0)
        img = Image.open(image)
        if img.format != 'PNG':
            raise forms.ValidationError("La firma deve essere un'immagine PNG.")

        width, height = img.size
        if width > MAX_SIGNATURE_WIDTH or height > MAX_SIGNATURE_HEIGHT:
            raise forms.ValidationError(
                f"Dimensioni immagine troppo grandi (max "
                f"{MAX_SIGNATURE_WIDTH}x{MAX_SIGNATURE_HEIGHT} px)."
            )

        image.seek(0)
        return image
