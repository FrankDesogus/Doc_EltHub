import base64

from django.contrib import admin
from django.utils.html import format_html

from accounts.models import UserSignature


@admin.register(UserSignature)
class UserSignatureAdmin(admin.ModelAdmin):
    """
    Sola visualizzazione: la firma resta modificabile solo dall'utente nella
    propria pagina impostazioni. L'anteprima è incorporata come data URI —
    mai un link diretto a image.url, perché nessuna view serve MEDIA_URL
    pubblicamente (coerente con TASK-028: nessuna firma esposta come file
    scaricabile senza controllo di accesso).
    """
    list_display = ('user', 'has_image', 'updated_at')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    readonly_fields = ('user', 'signature_preview', 'updated_at')
    fields = ('user', 'signature_preview', 'updated_at')

    @admin.display(boolean=True, description='Ha una firma')
    def has_image(self, obj):
        return bool(obj.image)

    @admin.display(description='Anteprima firma')
    def signature_preview(self, obj):
        if not obj.image:
            return 'Nessuna firma caricata.'
        try:
            with obj.image.open('rb') as fh:
                encoded = base64.b64encode(fh.read()).decode('ascii')
        except Exception as exc:
            return f'Firma presente ma il file non è leggibile dallo storage ({exc}).'
        return format_html(
            '<img src="data:image/png;base64,{}" '
            'style="max-width:300px;max-height:100px;background:#eee;border:1px solid #ccc;">',
            encoded,
        )

    def has_add_permission(self, request):
        return False
