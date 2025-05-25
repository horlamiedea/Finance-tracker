import asyncio
from asgiref.sync import sync_to_async
from celery import shared_task
from django.contrib.auth import get_user_model
from .services.gmail_service import GmailService
from transactions.models import Transaction, RawEmail
from datetime import datetime
from google.auth.exceptions import RefreshError
import os, re
from dateutil import parser as date_parser
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

@shared_task
def sync_transactions_task():
    users = User.objects.exclude(gmail_token__isnull=True)
    for user in users:
        credentials_json = {
            "token": user.gmail_token,
            "refresh_token": user.gmail_refresh_token,
            "client_id": os.getenv("GMAIL_CLIENT_ID"),
            "client_secret": os.getenv("GMAIL_CLIENT_SECRET"),
            "token_uri": "https://oauth2.googleapis.com/token"
        }

        gmail_service = GmailService(credentials_json)
        emails = gmail_service.fetch_emails(query='Debit OR Credit')

        for email_text in emails:
            parsed_transaction = gmail_service.parse_transaction(email_text, user)
            if parsed_transaction:
                Transaction.objects.get_or_create(**parsed_transaction)
# @shared_task
# def sync_user_transactions_task(user_id, start_date, end_date):
#     user = User.objects.get(id=user_id)
#     credentials_json = {
#         "token": user.gmail_token,
#         "refresh_token": user.gmail_refresh_token,
#         "client_id": os.getenv("GMAIL_CLIENT_ID"),
#         "client_secret": os.getenv("GMAIL_CLIENT_SECRET"),
#         "token_uri": "https://oauth2.googleapis.com/token"
#     }

#     gmail_service = GmailService(credentials_json)

#     query = f'after:{start_date.split("T")[0]} before:{end_date.split("T")[0]} (Debit OR Credit)'
#     emails = gmail_service.fetch_emails(query=query)

#     for email_text in emails:
#         parsed_transaction = gmail_service.parse_transaction(email_text, user)
#         if parsed_transaction:
#             transaction_date = date_parser.parse(parsed_transaction['date'])
#             parsed_transaction['date'] = transaction_date
#             Transaction.objects.get_or_create(**parsed_transaction)



def parse_transaction(self, email_text, user):
    # Convert email to lowercase for easier checks
    text_lower = email_text.lower()

    # Check if email contains 'debit' or 'credit' keyword
    if "debit" in text_lower:
        transaction_type = "debit"
        amount_match = re.search(r'debit amount\s*[:\n\r]*\s*([\d,]+\.\d{2})', email_text, re.IGNORECASE)
    elif "credit" in text_lower:
        transaction_type = "credit"
        amount_match = re.search(r'credit amount\s*[:\n\r]*\s*([\d,]+\.\d{2})', email_text, re.IGNORECASE)
    else:
        # No debit or credit found, skip
        return None

    if not amount_match:
        # fallback: find any amount in email (first number with decimals)
        amount_match = re.search(r'([\d,]+\.\d{2})', email_text)

    # Find date - try multiple date patterns to increase chances
    date_match = re.search(r'Date & Time\s*[:\n\r]*\s*([\d]{1,2} [A-Za-z]+, [\d]{4} \| [\d:]+ [AP]M)', email_text)
    if not date_match:
        # fallback to any date like DD/MM/YYYY or YYYY-MM-DD
        date_match = re.search(r'(\d{2}/\d{2}/\d{4})', email_text) or re.search(r'(\d{4}-\d{2}-\d{2})', email_text)

    narration_match = re.search(r'Narration\s*[:\n\r]*\s*(.+)', email_text)

    if amount_match and date_match:
        try:
            amount = float(amount_match.group(1).replace(',', ''))
        except Exception:
            amount = 0.0
        narration = narration_match.group(1).strip() if narration_match else 'N/A'
        date_str = date_match.group(1).strip()
        return {
            'user': user,
            'amount': amount,
            'account_balance': None,  # You can add parsing if available
            'date': date_str,
            'narration': narration,
            'transaction_type': transaction_type,
        }
    else:
        return None


@shared_task
def sync_user_transactions_task(user_id, start_date, end_date):
    user = User.objects.get(id=user_id)

    # Check OAuth credentials
    if not (user.gmail_token and user.gmail_refresh_token and
            os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET")):
        return f"Missing Gmail OAuth credentials for user {user_id}"

    credentials_dict = {
        "token": user.gmail_token,
        "refresh_token": user.gmail_refresh_token,
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "token_uri": "https://oauth2.googleapis.com/token",
    }

    gmail_service = GmailService(credentials_dict)

    query = f'after:{start_date.split("T")[0]} before:{end_date.split("T")[0]} (Debit OR Credit)'
    emails = gmail_service.fetch_emails(query=query)

    # Wrap ORM calls in sync_to_async for async context
    @sync_to_async
    def get_or_create_raw_email(user, email_id, email_text):
        return RawEmail.objects.get_or_create(
            user=user,
            email_id=email_id,
            defaults={"raw_text": email_text, "parsed": False, "parsing_method": "none"}
        )

    @sync_to_async
    def save_raw_email(raw_email_obj):
        raw_email_obj.save()

    @sync_to_async
    def create_transaction_if_not_exists(transaction_data):
        Transaction.objects.get_or_create(**transaction_data)

    async def process_email(email_text, idx):
        # Use unique email id based on user_id and email index
        email_id = f"{user_id}_{idx}"

        raw_email_obj, created = await get_or_create_raw_email(user, email_id, email_text)

        # Try to parse with regex-based parser
        parsed_transaction = gmail_service.parse_transaction(email_text, user)

        # If parsing fails or returns no transaction type, use AI parser async
        if not parsed_transaction or parsed_transaction.get('transaction_type') == 'none':
            # Call your async AI parse function here
            parsed_transaction = await gmail_service.ai_parse_transaction_async(email_text)

            raw_email_obj.parsing_method = 'ai'
        else:
            raw_email_obj.parsing_method = 'regex'

        # Mark raw email as parsed or not
        raw_email_obj.parsed = parsed_transaction.get('transaction_type', 'none') != 'none'
        raw_email_obj.transaction_data = parsed_transaction

        await save_raw_email(raw_email_obj)

        # If parsed successfully, normalize date and create transaction
        if raw_email_obj.parsed:
            try:
                # Normalize date: if string, parse; if already datetime, keep it
                date_value = parsed_transaction.get('date')
                if isinstance(date_value, str):
                    transaction_date = date_parser.parse(date_value)
                else:
                    transaction_date = date_value

                parsed_transaction['date'] = transaction_date

                await create_transaction_if_not_exists(parsed_transaction)
            except Exception as e:
                # Log or handle exceptions as needed
                print(f"Failed to create transaction for email #{idx}: {str(e)}")

    # Run all emails processing concurrently
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # No event loop in current thread, create one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    tasks = [process_email(email_text, idx + 1) for idx, email_text in enumerate(emails)]
    loop.run_until_complete(asyncio.gather(*tasks))

    return f"Transactions synced successfully for user {user_id}. Parsed: {len(emails)}, Processed: {len(tasks)}"