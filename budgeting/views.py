from rest_framework import viewsets
from budgeting.models import TransactionFrequency, ItemFrequency
from budgeting.serializers import TransactionFrequencySerializer, ItemFrequencySerializer
from rest_framework.permissions import IsAuthenticated

class TransactionFrequencyViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TransactionFrequencySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return TransactionFrequency.objects.filter(user=self.request.user)

class ItemFrequencyViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ItemFrequencySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ItemFrequency.objects.filter(user=self.request.user)
