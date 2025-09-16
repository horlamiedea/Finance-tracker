from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import generics, viewsets
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
from .pdf_generate import PDFReportGenerator

import io
from django.http import HttpResponse
from django.db import IntegrityError
from django.db.models import F
from django.db.models.functions import TruncMonth, TruncDay
import jwt
from django.core.management import call_command


# PDF and Charting Libraries
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.units import inch
import matplotlib.pyplot as plt
import numpy as np

class GmailTransactionSyncView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30) 

        sync_user_transactions_task.delay(user.id, start_date.isoformat(), end_date.isoformat())

        return Response({
            "status": "success",
            "message": f"Sync initiated for the last 30 days. Transactions will appear shortly."
        })



SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

class AuthorizeGmailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        expiration = datetime.utcnow() + timedelta(minutes=10)
        state_token = jwt.encode(
            {
                "user_id": request.user.id,
                "exp": expiration
            },
            settings.SECRET_KEY,
            algorithm="HS256"
        )

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
            scopes=['https://www.googleapis.com/auth/gmail.readonly'],
            redirect_uri=settings.GMAIL_REDIRECT_URI
        )

        authorization_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent',
            state=state_token
        )
        
        print(f"Authorization URL: {authorization_url}")
        return redirect(authorization_url)

class OAuth2CallbackView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        state_token = request.query_params.get('state')

        if not state_token:
            return Response({"error": "State token is missing."}, status=400)
        try:
            payload = jwt.decode(
                state_token, 
                settings.SECRET_KEY, 
                algorithms=["HS256"]
            )
            user_id = payload['user_id']
            user = User.objects.get(id=user_id)

        except jwt.ExpiredSignatureError:
            return Response({"error": "Authorization link has expired. Please try again."}, status=400)
        except (jwt.InvalidTokenError, User.DoesNotExist):
            return Response({"error": "Invalid authorization token. Please try again."}, status=400)
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
            scopes=['https://www.googleapis.com/auth/gmail.readonly'],
            state=state_token, # <-- Pass the original state token here
            redirect_uri=settings.GMAIL_REDIRECT_URI
        )

        try:
            flow.fetch_token(authorization_response=request.build_absolute_uri())
        except Exception as e:
            print(f"Error fetching token: {e}")
            return Response({"error": "Failed to fetch authorization token from Google."}, status=400)

        credentials = flow.credentials
        
        user.gmail_token = credentials.token
        if credentials.refresh_token:
            user.gmail_refresh_token = credentials.refresh_token
        user.save()

        # The HTML response to close the window is still a good idea
        return HttpResponse("<html><body><h1>Authentication Successful!</h1><p>You can now close this page.</p><script>window.close();</script></body></html>")




from rest_framework.pagination import PageNumberPagination

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 1000

class TransactionListView(generics.ListAPIView):
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        # Return transactions only for the authenticated user, ordered by date desc
        return Transaction.objects.filter(user=self.request.user).select_related('receipt', 'category').order_by('-date')



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
    

class BudgetSuggestionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        # Analyze last 90 days of spending for a 3-month average
        ninety_days_ago = timezone.now().date() - timedelta(days=90)
        
        spending_data = Transaction.objects.filter(
            user=user,
            transaction_type='debit',
            date__gte=ninety_days_ago,
            category__isnull=False
        ).values('category__id', 'category__name').annotate(
            total_spent=Sum('amount')
        ).order_by('-total_spent')

        if not spending_data:
            return Response({"message": "Not enough transaction data to suggest a budget."}, status=404)

        suggestions = []
        total_suggested_budget = 0
        for item in spending_data:
            # Average monthly spend = total over 90 days / 3
            monthly_avg = item['total_spent'] / 3
            suggestions.append({
                "category": item['category__id'],
                "category_name": item['category__name'],
                "budgeted_amount": round(float(monthly_avg), 2)
            })
            total_suggested_budget += monthly_avg

        response_data = {
            "name": "Suggested Monthly Budget",
            "start_date": timezone.now().date().replace(day=1),
            "end_date": (timezone.now().date().replace(day=1) + timedelta(days=31)).replace(day=1) - timedelta(days=1),
            "total_suggested_budget": round(float(total_suggested_budget), 2),
            "items": suggestions
        }
        return Response(response_data)


class BudgetViewSet(viewsets.ModelViewSet):
    serializer_class = BudgetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Budget.objects.filter(user=self.request.user).prefetch_related('items__category')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class EmailReportView(APIView):
    """
    Handles the request to email a financial report as a PDF attachment.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = request.user
        if not user.email:
            return Response(
                {"error": "Cannot send report. Please add an email address to your profile first."},
                status=400 # Bad Request
            )

        start_date_str = request.data.get('start_date')
        end_date_str = request.data.get('end_date')

        start_date = parse_date(start_date_str) if start_date_str else None
        end_date = parse_date(end_date_str) if end_date_str else None

        generate_and_email_report_task.delay(
            user.id,
            start_date.isoformat() if start_date else None,
            end_date.isoformat() if end_date else None
        )

        # 4. Return an immediate success response to the user
        return Response({
            "message": f"Your financial report is being generated and will be sent to {user.email} shortly."
        })

class PDFReportView(APIView):
    """
    Handles the request for a PDF report, validates parameters,
    and delegates the complex generation logic to the PDFReportGenerator.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # 1. Validate Query Parameters from the URL
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')

        start_date = parse_date(start_date_str) if start_date_str else None
        end_date = parse_date(end_date_str) if end_date_str else None

        # 2. Delegate to the Generator Service
        generator = PDFReportGenerator(user=request.user, start_date=start_date, end_date=end_date)
        pdf_buffer = generator.generate()

        # 3. Return the generated PDF as an HTTP Response
        response = HttpResponse(pdf_buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="financial_report_{datetime.now().strftime("%Y-%m-%d")}.pdf"'
        return response
    

class ReprocessFailedEmailsView(APIView):
    """
    An endpoint to manually trigger a re-scan and re-processing
    of any emails that previously failed to be converted into transactions.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        reprocess_failed_emails_task.delay(user.id)
        return Response({"message": "A task has been started to reprocess any failed emails. Please check your transactions again in a few minutes."})


class CleanTransactionNarrationsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            call_command('clean_narrations')
            return Response({"message": "Transaction narrations have been successfully cleaned."})
        except Exception as e:
            return Response({"error": str(e)}, status=500)
