import uuid
from django.db import models
from django.conf import settings

TRANSACTION_TYPES = (
    ('debit', 'Debit'),
    ('credit', 'Credit'),
)


class Bank(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="banks")
    name = models.CharField(max_length=100)
    is_excluded = models.BooleanField(default=False)

    class Meta:
        unique_together = ('user', 'name')

    def __str__(self):
        return f"{self.name} ({'Excluded' if self.is_excluded else 'Included'})"


class TransactionCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class UserCategoryMapping(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    transaction_category = models.ForeignKey(TransactionCategory, on_delete=models.CASCADE)
    keywords = models.JSONField(default=list)  # list of keywords that map to this category

    class Meta:
        unique_together = ('user', 'transaction_category')

    def __str__(self):
        return f"{self.user.username} - {self.transaction_category.name}"
class Transaction(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transactions")
    transaction_type = models.CharField(choices=(('debit', 'Debit'), ('credit', 'Credit')), max_length=10)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    date = models.DateTimeField()
    narration = models.TextField()
    category = models.ForeignKey(TransactionCategory, null=True, blank=True, on_delete=models.SET_NULL)
    bank_name = models.CharField(max_length=100, null=True, blank=True)
    account_balance = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    receipt_items = models.JSONField(null=True, blank=True) # For receipt uploads
    is_manually_categorized = models.BooleanField(default=False)
    narration_cleaned = models.BooleanField(default=False)

    class Meta:
        # This uniqueness constraint is key to preventing duplicates
        unique_together = ('user', 'amount', 'date', 'transaction_type')
        ordering = ['-date']

    def __str__(self):
        return f"{self.transaction_type.capitalize()} of ₦{self.amount} on {self.date}"


class Budget(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="budgets")
    name = models.CharField(max_length=100, default="Monthly Budget")
    start_date = models.DateField()
    end_date = models.DateField()
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    class Meta:
        unique_together = ('user', 'name', 'start_date')
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.name} ({self.user.username})"

class BudgetItem(models.Model):
    budget = models.ForeignKey(Budget, related_name='items', on_delete=models.CASCADE)
    category = models.ForeignKey(TransactionCategory, on_delete=models.CASCADE)
    budgeted_amount = models.DecimalField(max_digits=15, decimal_places=2)
    
    @property
    def spent_amount(self):
        # Calculate spent amount dynamically
        total_spent = Transaction.objects.filter(
            user=self.budget.user,
            category=self.category,
            transaction_type='debit',
            date__range=[self.budget.start_date, self.budget.end_date]
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        return total_spent
    
    @property
    def remaining_amount(self):
        return self.budgeted_amount - self.spent_amount

    def __str__(self):
        return f"{self.category.name} - ₦{self.budgeted_amount}"

class RawEmail(models.Model):
    """Stores raw email content before it's processed by the AI."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    email_id = models.CharField(max_length=255)
    raw_text = models.TextField()
    fetched_at = models.DateTimeField(auto_now_add=True)
    parsed = models.BooleanField(default=False)
    parsing_method = models.CharField(
        max_length=50,
        choices=[
            ('none', 'None'),
            ('dynamic_html_parser_success', 'Dynamic HTML Parser Success'),
            ('ai_generated_parser_success', 'AI Generated Parser Success'),
            ('ai_fallback_success', 'AI Fallback Success'),
            ('regex_fallback_success', 'Regex Fallback Success'),
            ('all_methods_failed', 'All Methods Failed'),
            ('creation_failed_data_error', 'Transaction Creation Failed (Data Error)'),
        ],
        default='none'
    )
    transaction_data = models.JSONField(null=True, blank=True)
    bank_name = models.CharField(max_length=100, null=True, blank=True)  # New field
    sent_date = models.DateTimeField(null=True, blank=True)  # New field
    manual_review_needed = models.BooleanField(default=False)  

    class Meta:
        unique_together = ('user', 'email_id')

    def __str__(self):
        return f"RawEmail {self.email_id} for {self.user}"



class UserTransactionCategorizationState(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    last_processed_date = models.DateTimeField(null=True, blank=True)



class ItemPurchaseFrequency(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    category = models.ForeignKey(TransactionCategory, on_delete=models.CASCADE)
    item_description = models.CharField(max_length=255)
    purchase_count = models.PositiveIntegerField(default=0)
    last_purchased = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'category', 'item_description')


class ParserFunction(models.Model):
    """Stores AI-generated Python code for parsing emails from a specific bank."""
    bank_name = models.CharField(max_length=100, unique=True)
    parser_code = models.TextField(help_text="The Python code for the parsing function.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Parser for {self.bank_name}"
