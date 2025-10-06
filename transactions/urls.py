from django.urls import path, include
from .views import *
from rest_framework.routers import DefaultRouter
from .views import BudgetViewSet, BankViewSet


router = DefaultRouter()
router.register(r'budgets', BudgetViewSet, basename='budget')
router.register(r'banks', BankViewSet, basename='bank')

urlpatterns = [
    path('sync-gmail/', GmailTransactionSyncView.as_view(), name='sync-gmail-transactions'),
    path('authorize-gmail/', AuthorizeGmailView.as_view(), name='authorize_gmail'),
    path('oauth2callback/', OAuth2CallbackView.as_view(), name='oauth2callback'),
    path('get/', TransactionListView.as_view(), name='transaction-list'),
    path('<uuid:pk>/', TransactionUpdateView.as_view(), name='transaction-update'),
    path('budget-suggestion/', BudgetSuggestionView.as_view(), name='budget-suggestion'),
    path('categorize/', CategorizeUserTransactionsView.as_view(), name='categorize-transactions'),
    path('summary/', TransactionSummaryView.as_view(), name='transaction-summary'),
    path('spending-statistics/', SpendingStatisticsView.as_view(), name='spending-statistics'),
    path('report/download/', PDFReportView.as_view(), name='download-pdf-report'),
    path('report/email/', EmailReportView.as_view(), name='email-pdf-report'),
    path('reprocess-failed/', ReprocessFailedEmailsView.as_view(), name='reprocess-failed-emails'),
    path('clean-narrations/', CleanTransactionNarrationsView.as_view(), name='clean-narrations'),

    path('', include(router.urls)),
]
