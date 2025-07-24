from django.urls import path, include
from .views import *
from rest_framework.routers import DefaultRouter
from .views import BudgetViewSet


router = DefaultRouter()
router.register(r'budgets', BudgetViewSet, basename='budget')

urlpatterns = [
    path('sync-gmail/', GmailTransactionSyncView.as_view(), name='sync-gmail-transactions'),
    path('authorize-gmail/', AuthorizeGmailView.as_view(), name='authorize_gmail'),
    path('oauth2callback/', OAuth2CallbackView.as_view(), name='oauth2callback'),
    path('get/', TransactionListView.as_view(), name='transaction-list'),
    path('<int:pk>/', TransactionUpdateView.as_view(), name='transaction-update'),
    path('budget-suggestion/', BudgetSuggestionView.as_view(), name='budget-suggestion'),
    path('categorize/', CategorizeUserTransactionsView.as_view(), name='categorize-transactions'),
    path('summary/', TransactionSummaryView.as_view(), name='transaction-summary'),
    path('spending-statistics/', SpendingStatisticsView.as_view(), name='spending-statistics'),
    path('report/download/', PDFReportView.as_view(), name='download-pdf-report'),

    path('budget/', include(router.urls)),
]
