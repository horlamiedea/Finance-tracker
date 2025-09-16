from rest_framework import serializers
from budgeting.models import TransactionFrequency, ItemFrequency

class TransactionFrequencySerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionFrequency
        fields = '__all__'

class ItemFrequencySerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemFrequency
        fields = '__all__'
