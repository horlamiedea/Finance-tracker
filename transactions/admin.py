from django.contrib import admin

# Register your models here.
from .models import Transaction, RawEmail


admin.site.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """Admin interface for Transaction model."""
    search_fields = ('user__username', 'transaction_type')
    ordering = ('-date',)
    fieldsets = (
        (None, {'fields': ('user', 'amount', 'date', 'transaction_type')}),
    )
    add_fieldsets = fieldsets
    readonly_fields = ('date',)
    list_display = ('user', 'amount', 'date', 'transaction_type')

admin.site.register(RawEmail)
class RawEmailAdmin(admin.ModelAdmin):
    """Admin interface for RawEmail model."""
    search_fields = ('user__username', 'email_id')
    ordering = ('-fetched_at',)
    fieldsets = (
        (None, {'fields': ('user', 'email_id', 'raw_text', 'fetched_at')}),
        ('Parsing Info', {'fields': ('parsed', 'parsing_method', 'transaction_data')}),
    )
    add_fieldsets = fieldsets
    readonly_fields = ('fetched_at',)