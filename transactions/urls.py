from django.urls import path
from .views import *

urlpatterns = [
    path('sync-gmail/', GmailTransactionSyncView.as_view(), name='sync-gmail-transactions'),
    path('authorize-gmail/', AuthorizeGmailView.as_view(), name='authorize_gmail'),
    path('oauth2callback/', OAuth2CallbackView.as_view(), name='oauth2callback'),
]
