from rest_framework import serializers
from .models import *
from receipts.models import Receipt


class TransactionCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionCategory
        fields = ['id', 'name']
class ReceiptSerializer(serializers.ModelSerializer):
    uploaded_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Receipt
        fields = ['id', 'uploaded_image_url', 'extracted_text', 'items', 'upload_date']

    def get_uploaded_image_url(self, obj):
        request = self.context.get('request')
        if obj.uploaded_image and request:
            return request.build_absolute_uri(obj.uploaded_image.url)
        return None

class TransactionSerializer(serializers.ModelSerializer):
    receipt = serializers.SerializerMethodField()
    category = TransactionCategorySerializer(read_only=True)

    class Meta:
        model = Transaction
        fields = ['id', 'transaction_type', 'amount', 'date', 'narration', 
                  'account_balance', 'sender_receiver', 'reference_id', 'receipt', 'category']

    def get_receipt(self, obj):
        try:
            receipt = obj.receipt
            return ReceiptSerializer(receipt, context=self.context).data
        except Receipt.DoesNotExist:
            return None


class TransactionUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            'transaction_type',
            'amount',
            'date',
            'narration',
            'account_balance',
            'sender_receiver',
            'reference_id',
        ]
        read_only_fields = ['user']