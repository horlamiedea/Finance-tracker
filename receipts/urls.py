from django.urls import path
from .views import ReceiptProcessView, LinkReceiptToTransactionView

urlpatterns = [
    path('upload/', ReceiptProcessView.as_view(), name='receipt-upload'),
    path('link-to-transaction/<int:transaction_id>/', LinkReceiptToTransactionView.as_view(), name='link-receipt-to-transaction'),
]
