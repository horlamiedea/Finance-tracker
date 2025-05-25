from django.urls import path
from .views import ReceiptProcessView

urlpatterns = [
    path('upload/', ReceiptProcessView.as_view(), name='receipt-upload'),
]
