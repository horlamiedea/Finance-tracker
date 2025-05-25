from django.db import models
from django.conf import settings

TRANSACTION_TYPES = (
    ('debit', 'Debit'),
    ('credit', 'Credit'),
)

class Transaction(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)  # Fix here
    transaction_type = models.CharField(choices=TRANSACTION_TYPES, max_length=10)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    date = models.DateTimeField()
    narration = models.TextField()
    account_balance = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    sender_receiver = models.CharField(max_length=255, null=True, blank=True)
    reference_id = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        unique_together = ('user', 'amount', 'date', 'transaction_type')

    def __str__(self):
        return f"{self.transaction_type.capitalize()} of ₦{self.amount} on {self.date}"
