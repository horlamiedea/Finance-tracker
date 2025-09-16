from django.urls import path, include
from rest_framework.routers import DefaultRouter
from budgeting.views import TransactionFrequencyViewSet, ItemFrequencyViewSet

router = DefaultRouter()
router.register(r'transaction-frequency', TransactionFrequencyViewSet, basename='transaction-frequency')
router.register(r'item-frequency', ItemFrequencyViewSet, basename='item-frequency')

urlpatterns = [
    path('', include(router.urls)),
]
