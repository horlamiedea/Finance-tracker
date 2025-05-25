from django.contrib import admin

# Register your models here.
from .models import Receipt

admin.site.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    """Admin interface for Receipt model."""
    search_fields = ('user__username', 'upload_date')
    ordering = ('-upload_date',)
    fieldsets = (
        (None, {'fields': ('user', 'extracted_text', 'items', 'upload_date')}),
    )
    add_fieldsets = fieldsets
    readonly_fields = ('user', 'extracted_text', 'items', 'upload_date')
    list_display = ('user', 'upload_date', 'extracted_text')