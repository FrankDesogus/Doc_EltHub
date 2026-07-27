from django.contrib import admin

from accounts.models import UserSignature


@admin.register(UserSignature)
class UserSignatureAdmin(admin.ModelAdmin):
    list_display = ('user', 'image', 'updated_at')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    readonly_fields = ('updated_at',)
