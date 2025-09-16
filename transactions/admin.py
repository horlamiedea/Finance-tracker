from django.contrib import admin

# Register your models here.
from .models import *


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """Admin interface for Transaction model."""
    search_fields = ('user__username', 'transaction_type', 'narration', 'bank_name')
    list_display = ('user', 'amount', 'date', 'transaction_type', 'narration', 'category', 'bank_name')
    list_filter = ('transaction_type', 'category', 'bank_name', 'is_manually_categorized')
    ordering = ('-date',)
    fieldsets = (
        (None, {'fields': ('user', 'amount', 'date', 'transaction_type', 'narration')}),
        ('Details', {'fields': ('category', 'bank_name', 'account_balance', 'is_manually_categorized')}),
    )
    readonly_fields = ('date',)

@admin.register(RawEmail)
class RawEmailAdmin(admin.ModelAdmin):
    """Admin interface for RawEmail model."""
    search_fields = ('user__username', 'email_id', 'bank_name')
    list_display = ('user', 'email_id', 'bank_name', 'sent_date', 'parsed', 'parsing_method', 'manual_review_needed')
    list_filter = ('parsed', 'manual_review_needed', 'parsing_method', 'bank_name')
    ordering = ('-fetched_at',)
    fieldsets = (
        (None, {'fields': ('user', 'email_id', 'raw_text', 'fetched_at', 'bank_name', 'sent_date')}),
        ('Parsing Info', {'fields': ('parsed', 'parsing_method', 'transaction_data', 'manual_review_needed')}),
    )
    readonly_fields = ('fetched_at', 'transaction_data')


admin.site.register(TransactionCategory)
class TransactionCategoryAdmin(admin.ModelAdmin):
    """Admin interface for TransactionCategory model."""
    search_fields = ('name',)
    ordering = ('name',)
    fieldsets = (
        (None, {'fields': ('name',)}),
    )
    add_fieldsets = fieldsets
    list_display = ('name',)
admin.site.register(UserCategoryMapping)
class UserCategoryMappingAdmin(admin.ModelAdmin):
    """Admin interface for UserCategoryMapping model."""
    search_fields = ('user__username', 'transaction_category__name')
    ordering = ('user', 'transaction_category')
    fieldsets = (
        (None, {'fields': ('user', 'transaction_category')}),
        ('Keywords', {'fields': ('keywords',)}),
    )
    add_fieldsets = fieldsets
    list_display = ('user', 'transaction_category')

admin.site.register(UserTransactionCategorizationState)
class UserTransactionCategorizationStateAdmin(admin.ModelAdmin):
    """Admin interface for UserTransactionCategorizationState model."""
    search_fields = ('user__username',)
    ordering = ('user',)
    fieldsets = (
        (None, {'fields': ('user', 'state')}),
    )
    add_fieldsets = fieldsets
    list_display = ('user', 'state')


admin.site.register(ItemPurchaseFrequency)
class ItemPurchaseFrequencyAdmin(admin.ModelAdmin):
    """Admin interface for ItemPurchaseFrequency model."""
    search_fields = ('user__username', 'item_name')
    ordering = ('user', 'item_name')
    fieldsets = (
        (None, {'fields': ('user', 'item_name', 'frequency')}),
    )
    add_fieldsets = fieldsets
    list_display = ('user', 'item_name', 'frequency')

admin.site.register(ParserFunction)
class ParserFunctionAdmin(admin.ModelAdmin):
    """Admin interface for ParserFunction model."""
    search_fields = ('name',)
    ordering = ('name',)
    fieldsets = (
        (None, {'fields': ('name', 'description', 'function_code')}),
    )
    add_fieldsets = fieldsets
    list_display = ('name', 'description')
