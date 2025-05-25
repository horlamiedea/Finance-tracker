from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from datetime import datetime
from django.shortcuts import redirect
from google_auth_oauthlib.flow import Flow
from django.conf import settings
from django.utils import timezone
from .tasks import sync_user_transactions_task
from transactions.models import Transaction
from datetime import datetime, timedelta

class GmailTransactionSyncView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        
        # Check the latest transaction date for the user
        last_transaction = Transaction.objects.filter(user=user).order_by('-date').first()

        if last_transaction:
            # If exists, start sync from last transaction date
            start_date = last_transaction.date
        else:
            # Else, start from the beginning of the current month
            today = timezone.now()
            start_date = timezone.make_aware(datetime(today.year, today.month, 1))

        end_date = timezone.now()

        # Trigger async Celery task
        sync_user_transactions_task.delay(user.id, start_date.isoformat(), end_date.isoformat())

        return Response({
            "status": "success",
            "message": f"Sync initiated from {start_date.date()} to {end_date.date()}"
        })



SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

class AuthorizeGmailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        flow = Flow.from_client_config(
            client_config={
                "web": {
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [settings.GMAIL_REDIRECT_URI],
                }
            },
            scopes=SCOPES,
        )
        flow.redirect_uri = settings.GMAIL_REDIRECT_URI

        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        print(f"Authorization URL: {authorization_url}")
        request.session['oauth_state'] = state
        return redirect(authorization_url)


class OAuth2CallbackView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        state = request.session.get('oauth_state')

        flow = Flow.from_client_config(
            client_config={
                "web": {
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [settings.GMAIL_REDIRECT_URI],
                }
            },
            scopes=SCOPES,
            state=state,
        )
        flow.redirect_uri = settings.GMAIL_REDIRECT_URI

        authorization_response = request.build_absolute_uri()
        flow.fetch_token(authorization_response=authorization_response)

        credentials = flow.credentials
        user = request.user
        user.gmail_token = credentials.token
        user.gmail_refresh_token = credentials.refresh_token
        user.save()

        return Response({"detail": "Google authorization successful."})