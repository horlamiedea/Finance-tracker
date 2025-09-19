from rest_framework import serializers
from .models import Receipt

class ReceiptSerializer(serializers.ModelSerializer):

    class Meta:
        model = Receipt
        fields = ('id', 'transaction', 'user', 'uploaded_image_url', 'extracted_text', 'items', 'upload_date')
        read_only_fields = ('user', 'extracted_text', 'items', 'upload_date', 'uploaded_image_url')
