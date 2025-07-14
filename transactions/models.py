from django.db import models
from django.conf import settings

TRANSACTION_TYPES = (
    ('debit', 'Debit'),
    ('credit', 'Credit'),
)
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
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    transaction_type = models.CharField(choices=(('debit', 'Debit'), ('credit', 'Credit')), max_length=10)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    date = models.DateTimeField()
    narration = models.TextField()
    category = models.ForeignKey('TransactionCategory', null=True, blank=True, on_delete=models.SET_NULL)
    account_balance = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    sender_receiver = models.CharField(max_length=255, null=True, blank=True)
    reference_id = models.CharField(max_length=255, null=True, blank=True)
    receipt_items = models.JSONField(null=True, blank=True)
    bank_name = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        unique_together = ('user', 'amount', 'date', 'transaction_type')

    def __str__(self):
        return f"{self.transaction_type.capitalize()} of ₦{self.amount} on {self.date}"




class RawEmail(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    email_id = models.CharField(max_length=255, unique=True)
    raw_text = models.TextField()
    fetched_at = models.DateTimeField(auto_now_add=True)
    parsed = models.BooleanField(default=False)
    parsing_method = models.CharField(
        max_length=50,
        choices=[('regex', 'Regex'), ('bs4', 'BeautifulSoup'), ('none', 'None')],
        default='none'
    )
    transaction_data = models.JSONField(null=True, blank=True)

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