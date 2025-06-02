from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from datetime import datetime
from django.shortcuts import redirect
from google_auth_oauthlib.flow import Flow
from django.conf import settings
from django.utils import timezone
from .tasks import *
from transactions.models import Transaction
from rest_framework import generics
from .models import Transaction
from .serializers import *
from datetime import datetime, timedelta
from django.utils.dateparse import parse_date
from django.db.models import Sum, Count, Q

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





class TransactionListView(generics.ListAPIView):
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Return transactions only for the authenticated user, ordered by date desc
        return Transaction.objects.filter(user=self.request.user).order_by('-date')



class TransactionUpdateView(generics.RetrieveUpdateAPIView):
    serializer_class = TransactionUpdateSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Only allow user to update their own transactions
        return Transaction.objects.filter(user=self.request.user)



class CategorizeUserTransactionsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        categorize_transactions_for_user.delay(user.id)
        return Response({"message": "Categorization started for your transactions."})



class TransactionSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        start_date = request.query_params.get('startdate')
        end_date = request.query_params.get('enddate')

        filters = {'user': user}

        if start_date:
            parsed_start = parse_date(start_date)
            if parsed_start:
                filters['date__gte'] = parsed_start
        if end_date:
            parsed_end = parse_date(end_date)
            if parsed_end:
                filters['date__lte'] = parsed_end

        debit_agg = Transaction.objects.filter(**filters, transaction_type='debit').aggregate(
            total_amount=Sum('amount'),
            total_count=Count('id')
        )
        credit_agg = Transaction.objects.filter(**filters, transaction_type='credit').aggregate(
            total_amount=Sum('amount'),
            total_count=Count('id')
        )

        total_debit = debit_agg["total_amount"] or 0
        total_credit = credit_agg["total_amount"] or 0

        data = {
            "debit": {
                "total_count": debit_agg["total_count"] or 0,
                "total_amount": float(total_debit)
            },
            "credit": {
                "total_count": credit_agg["total_count"] or 0,
                "total_amount": float(total_credit)
            },
            "balance": float(total_credit - total_debit)
        }
        return Response(data)


class SpendingStatisticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        start_date = request.query_params.get('startdate')
        end_date = request.query_params.get('enddate')

        filters = {'user': user, 'transaction_type': 'debit'}  # only spending

        if start_date:
            parsed_start = parse_date(start_date)
            if parsed_start:
                filters['date__gte'] = parsed_start

        if end_date:
            parsed_end = parse_date(end_date)
            if parsed_end:
                filters['date__lte'] = parsed_end

        qs = Transaction.objects.filter(**filters).values('category__name').annotate(
            total_amount=Sum('amount'),
            transaction_count=Count('id')
        ).order_by('-total_amount')

        # Format response
        data = {
            "spending_by_category": [
                {
                    "category": entry['category__name'] or "Uncategorized",
                    "total_amount": float(entry['total_amount'] or 0),
                    "transaction_count": entry['transaction_count']
                } for entry in qs
            ]
        }

        return Response(data)