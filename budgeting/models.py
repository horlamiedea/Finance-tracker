from django.db import models
from django.conf import settings
from transactions.models import TransactionCategory

class TransactionFrequency(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    narration = models.CharField(max_length=255)
    frequency = models.CharField(max_length=50, null=True, blank=True)  # e.g., 'daily', 'weekly', 'monthly'
    transaction_count = models.PositiveIntegerField(default=0)
    last_transaction_date = models.DateTimeField(null=True, blank=True)
    next_predicted_date = models.DateTimeField(null=True, blank=True)
    confidence_score = models.FloatField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'narration')

    def __str__(self):
        return f"{self.narration} - {self.frequency}"

class ItemFrequency(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    item_description = models.CharField(max_length=255)
    category = models.ForeignKey(TransactionCategory, on_delete=models.CASCADE)
    frequency = models.CharField(max_length=50, null=True, blank=True) # e.g., 'daily', 'weekly', 'monthly'
    purchase_count = models.PositiveIntegerField(default=0)
    last_purchased = models.DateTimeField(null=True, blank=True)
    next_predicted_date = models.DateTimeField(null=True, blank=True)
    confidence_score = models.FloatField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'item_description')

    def __str__(self):
        return f"{self.item_description} - {self.frequency}"
