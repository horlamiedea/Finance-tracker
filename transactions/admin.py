from django.contrib import admin

# Register your models here.
from .models import Transaction


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