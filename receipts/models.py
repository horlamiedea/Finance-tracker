from django.conf import settings
from django.db import models
from transactions.models import Transaction

class Receipt(models.Model):
    transaction = models.OneToOneField(Transaction, on_delete=models.SET_NULL, null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)  # Fix here
    uploaded_image = models.ImageField(upload_to='receipts/')
    extracted_text = models.TextField(blank=True, null=True)
    items = models.JSONField(null=True, blank=True)
    upload_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Receipt for ₦{self.transaction.amount if self.transaction else 'Unknown'} ({self.user.username})"
