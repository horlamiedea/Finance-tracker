from django.conf import settings
from django.db import models
from transactions.models import Transaction
from .azure_service import AzureBlobStorage
import uuid

class Receipt(models.Model):
    transaction = models.OneToOneField(Transaction, on_delete=models.SET_NULL, null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    uploaded_image_url = models.URLField(max_length=1024, blank=True, null=True)
    extracted_text = models.TextField(blank=True, null=True)
    items = models.JSONField(null=True, blank=True)
    upload_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Receipt for ₦{self.transaction.amount if self.transaction else 'Unknown'} ({self.user.username})"

    def upload_to_azure(self, file):
        azure_blob_storage = AzureBlobStorage()
        blob_name = f"receipts/{self.user.id}/{uuid.uuid4()}_{file.name}"
        self.uploaded_image_url = azure_blob_storage.upload_blob(file, blob_name)
        self.save()
