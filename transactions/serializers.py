from rest_framework import serializers
from .models import *
from receipts.models import Receipt


class BankSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bank
        fields = ['id', 'name', 'is_excluded']


class TransactionCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionCategory
        fields = ['id', 'name']
class ReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Receipt
        fields = ['id', 'uploaded_image_url', 'extracted_text', 'items', 'upload_date']

class TransactionSerializer(serializers.ModelSerializer):
    receipt = ReceiptSerializer(read_only=True)
    category = TransactionCategorySerializer(read_only=True)

    class Meta:
        model = Transaction
        fields = ['id', 'transaction_type', 'amount', 'date', 'narration', 
                  'account_balance', 'receipt', 'category']


class TransactionUpdateSerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(
        queryset=TransactionCategory.objects.all(), 
        required=False
    )

    class Meta:
        model = Transaction
        fields = ['category']



class BudgetItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    spent_amount = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    remaining_amount = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)

    class Meta:
        model = BudgetItem
        fields = (
            'id', 'category', 'category_name', 'budgeted_amount', 
            'spent_amount', 'remaining_amount'
        )
        # Category is write-only, category_name is read-only
        extra_kwargs = {'category': {'write_only': True}}


class BudgetSerializer(serializers.ModelSerializer):
    items = BudgetItemSerializer(many=True)
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Budget
        fields = ('id', 'user', 'name', 'start_date', 'end_date', 'total_amount', 'items')
        read_only_fields = ('user', 'total_amount')

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        
        # Calculate total amount from the sum of budget items
        total_amount = sum(item['budgeted_amount'] for item in items_data)
        validated_data['total_amount'] = total_amount
        
        budget = Budget.objects.create(**validated_data)
        
        for item_data in items_data:
            BudgetItem.objects.create(budget=budget, **item_data)
        return budget
