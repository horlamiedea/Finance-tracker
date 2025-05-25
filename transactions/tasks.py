from celery import shared_task
from django.contrib.auth import get_user_model
from .services.gmail_service import GmailService
from transactions.models import Transaction
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

# @shared_task
# def sync_user_transactions_task(user_id, start_date, end_date):
#     user = User.objects.get(id=user_id)

#     if not (user.gmail_token and user.gmail_refresh_token and
#             os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET")):
#         logger.error(f"Missing Gmail OAuth credentials for user {user_id}")
#         return f"Missing Gmail OAuth credentials for user {user_id}"

#     credentials_dict = {
#         "token": user.gmail_token,
#         "refresh_token": user.gmail_refresh_token,
#         "client_id": os.getenv("GOOGLE_CLIENT_ID"),
#         "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
#         "token_uri": "https://oauth2.googleapis.com/token",
#     }

#     try:
#         gmail_service = GmailService(credentials_dict)

#         query = f'after:{start_date.split("T")[0]} before:{end_date.split("T")[0]} (Debit OR Credit)'
#         emails = gmail_service.fetch_emails(query=query)
#         logger.info(f"User {user_id}: Fetched {len(emails)} emails with query: {query}")

#         created_count = 0
#         parsed_count = 0
#         for idx, email_text in enumerate(emails, start=1):
#             parsed_transaction = gmail_service.parse_transaction(email_text, user)
#             if parsed_transaction:
#                 parsed_count += 1
#                 transaction_date = date_parser.parse(parsed_transaction['date'])
#                 parsed_transaction['date'] = transaction_date

#                 obj, created = Transaction.objects.get_or_create(**parsed_transaction)
#                 if created:
#                     created_count += 1
#                     logger.info(f"User {user_id}: Created transaction #{created_count} from email #{idx}: {obj}")
#                 else:
#                     logger.info(f"User {user_id}: Transaction already exists for email #{idx}: {obj}")
#             else:
#                 logger.warning(f"User {user_id}: No transaction parsed from email #{idx}")

#         logger.info(f"User {user_id}: Parsed {parsed_count} transactions, created {created_count} new transactions.")

#     except RefreshError as e:
#         logger.error(f"User {user_id}: Failed to refresh token: {str(e)}")
#         return f"Failed to refresh token for user {user_id}: {str(e)}"
#     except Exception as e:
#         logger.error(f"User {user_id}: Unexpected error during sync: {str(e)}")
#         return f"Unexpected error for user {user_id}: {str(e)}"

#     return f"Transactions synced successfully for user {user_id}. Parsed: {parsed_count}, Created: {created_count}"



@shared_task
def sync_user_transactions_task(user_id, start_date, end_date):
    user = User.objects.get(id=user_id)

    # Check if credentials exist
    if not (user.gmail_token and user.gmail_refresh_token and
            os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET")):
        msg = f"Missing Gmail OAuth credentials for user {user_id}"
        logger.error(msg)
        return msg

    credentials_dict = {
        "token": user.gmail_token,
        "refresh_token": user.gmail_refresh_token,
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "token_uri": "https://oauth2.googleapis.com/token",
    }

    try:
        gmail_service = GmailService(credentials_dict)
        query = f'after:{start_date.split("T")[0]} before:{end_date.split("T")[0]} (Debit OR Credit)'
        emails = gmail_service.fetch_emails(query=query)
        logger.info(f"User {user_id}: Fetched {len(emails)} emails with query: {query}")

        parsed_count = 0
        created_count = 0

        for idx, email_text in enumerate(emails, start=1):
            snippet = email_text[:500].replace('\n', ' ').replace('\r', ' ')
            logger.warning(f"Email snippet (first 500 chars): {snippet}")
            parsed_transaction = gmail_service.parse_transaction(email_text, user)

            if not parsed_transaction:
                logger.warning(f"Email #{idx}: No transaction parsed")
                continue

            # Safely parse date only if it's a string
            date_value = parsed_transaction['date']
            if not isinstance(date_value, datetime):
                try:
                    transaction_date = date_parser.parse(date_value)
                except Exception as e:
                    logger.error(f"Email #{idx}: Date parsing failed for '{date_value}': {e}")
                    continue
            else:
                transaction_date = date_value

            parsed_transaction['date'] = transaction_date
            parsed_count += 1

            transaction_obj, created = Transaction.objects.get_or_create(**parsed_transaction)
            if created:
                created_count += 1

        logger.info(f"User {user_id}: Parsed {parsed_count} transactions, created {created_count} new ones.")
        return f"Transactions synced successfully for user {user_id}. Parsed: {parsed_count}, Created: {created_count}"

    except RefreshError as e:
        msg = f"Failed to refresh token for user {user_id}: {str(e)}"
        logger.error(msg)
        return msg

    except Exception as e:
        msg = f"Unexpected error syncing transactions for user {user_id}: {str(e)}"
        logger.error(msg)
        return msg