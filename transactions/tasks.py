import asyncio
from asgiref.sync import sync_to_async
from celery import shared_task
from django.contrib.auth import get_user_model
from .services.gmail_service import GmailService
from transactions.models import *
from decimal import Decimal
from datetime import datetime
from google.auth.exceptions import RefreshError
import os, re
from openai import OpenAI
from dateutil import parser as date_parser
import logging

logger = logging.getLogger(__name__)
User = get_user_model()
client = OpenAI(api_key=settings.OPENAI_API_KEY)

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


@sync_to_async
def create_transaction_if_not_exists(transaction_data):
    """Create transaction with proper field types."""
    try:
        logger.info(f"Attempting to create transaction: {transaction_data}")
        transaction, created = Transaction.objects.get_or_create(
            user=transaction_data['user'],
            amount=Decimal(transaction_data['amount']),
            date=transaction_data['date'],
            transaction_type=transaction_data['transaction_type'],
            defaults={
                'narration': transaction_data.get('narration', 'N/A'),
                'account_balance': Decimal(transaction_data['account_balance']) if transaction_data.get('account_balance') else None,
                'bank_name': transaction_data['bank_name'],
            }
        )
        if created:
            logger.info(f"Transaction created: {transaction}")
        else:
            logger.info(f"Transaction already exists: {transaction}")
        return transaction, created
    except Exception as e:
        logger.error(f"Error creating transaction: {str(e)}")
        return None, False

@shared_task
def sync_user_transactions_task(user_id, start_date, end_date):
    user = User.objects.get(id=user_id)
    if not (user.gmail_token and user.gmail_refresh_token and
            os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET")):
        logger.error(f"Missing Gmail OAuth credentials for user {user_id}")
        return f"Missing Gmail OAuth credentials for user {user_id}"

    credentials_dict = {
        "token": user.gmail_token,
        "refresh_token": user.gmail_refresh_token,
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "token_uri": "https://oauth2.googleapis.com/token",
    }

    gmail_service = GmailService(credentials_dict)
    last_sync_date = start_date.split("T")[0]
    query = f'after:{last_sync_date} (Debit OR Credit)'
    emails = gmail_service.fetch_emails(query=query)

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

    async def process_email(email_details, idx):
        email_text = email_details['body']
        headers = email_details['headers']
        email_id = f"{user_id}_{idx}"
        raw_email_obj, created = await get_or_create_raw_email(user, email_id, email_text)
        
        # Extract bank name and parse with BeautifulSoup
        bank_name = gmail_service.get_bank_name(headers)
        parsed_transaction = gmail_service.parse_transaction(email_text, bank_name)
        
        raw_email_obj.parsing_method = 'bs4'
        raw_email_obj.parsed = parsed_transaction.get('transaction_type', 'none') != 'none'
        raw_email_obj.transaction_data = parsed_transaction
        await save_raw_email(raw_email_obj)

        if raw_email_obj.parsed:
            try:
                # Add user to transaction_data for transaction creation
                transaction_data = parsed_transaction.copy()
                transaction_data['user'] = user
                transaction_data['date'] = date_parser.parse(parsed_transaction['date'])
                await create_transaction_if_not_exists(transaction_data)
            except Exception as e:
                logger.error(f"Failed to create transaction for email #{idx}: {str(e)}")

    try:
        loop = asyncio.get_event_loop()
    except:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    tasks = [process_email(email_details, idx + 1) for idx, email_details in enumerate(emails)]
    loop.run_until_complete(asyncio.gather(*tasks))

    return f"Transactions synced successfully for user {user_id}. Parsed: {len(emails)}, Processed: {len(tasks)}"

@shared_task
def categorize_transactions_for_all_users():
    users = User.objects.all()
    for user in users:
        categorize_transactions_for_user.delay(user.id)


@shared_task
def categorize_transactions_for_user(user_id):
    user = User.objects.get(id=user_id)
    state, created = UserTransactionCategorizationState.objects.get_or_create(user=user)
    last_processed = state.last_processed_date or '1970-01-01T00:00:00Z'

    transactions = Transaction.objects.filter(
        user=user,
        date__gt=last_processed,
        category__isnull=True
    ).order_by('date')

    if not transactions.exists():
        logger.info(f"No new transactions to categorize for user {user.username}")
        return "No new transactions to categorize."

    # Fetch all categories from DB
    categories = list(TransactionCategory.objects.values_list('name', flat=True))

    # User keyword mappings
    user_mappings = UserCategoryMapping.objects.filter(user=user)
    user_keyword_map = {}
    for mapping in user_mappings:
        for keyword in mapping.keywords:
            user_keyword_map[keyword.lower()] = mapping.transaction_category.name

    for tx in transactions:
        narration_lower = tx.narration.lower()
        matched_category = None

        # First, check user-defined keywords
        for keyword, cat_name in user_keyword_map.items():
            if keyword in narration_lower:
                matched_category = TransactionCategory.objects.get(name=cat_name)
                break

        # Next, if no match, try AI categorization
        if not matched_category:
            prompt = f"""
You are a helpful assistant that categorizes financial transactions into one of these categories:
{', '.join(categories)}.

Transaction narration: "{tx.narration}"
Receipt items: {tx.receipt_items or []}

Pick the best category from the list above or respond with "Unknown" if unsure.
Respond ONLY with the category name.
"""
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=10,
                    temperature=0.2,
                )
                category_name = response.choices[0].message.content.strip()
                if category_name not in categories:
                    category_name = "Unknown"
                matched_category, _ = TransactionCategory.objects.get_or_create(name=category_name)
            except Exception as e:
                logger.error(f"OpenAI API error for user {user.username} transaction {tx.id}: {e}")
                matched_category, _ = TransactionCategory.objects.get_or_create(name="Unknown")
                category_name = response.choices[0].message.content.strip()

                if category_name == "Unknown" or category_name not in categories:
                    similar_tx = Transaction.objects.filter(
                        user=user,
                        narration__icontains=tx.narration[:30],
                    ).exclude(category__isnull=True).first()

                    if similar_tx and similar_tx.category:
                        matched_category = similar_tx.category
                    else:
                        matched_category, _ = TransactionCategory.objects.get_or_create(name="Unknown")
                else:
                    matched_category, _ = TransactionCategory.objects.get_or_create(name=category_name)

        tx.category = matched_category
        tx.save()

        # Update purchase frequency for each item in receipt_items
        items = tx.receipt_items or []
        for item in items:
            description = item.get("description", "").lower()
            if not description:
                continue
            freq_obj, created = ItemPurchaseFrequency.objects.get_or_create(
                user=user,
                item_description=description,
                defaults={"category": matched_category, "purchase_count": 0, "last_purchased": tx.date}
            )
            freq_obj.purchase_count += 1
            freq_obj.last_purchased = max(freq_obj.last_purchased, tx.date) if freq_obj.last_purchased else tx.date
            freq_obj.save()

    # Update last processed date safely
    last_transaction = transactions.last()
    if last_transaction:
        state.last_processed_date = last_transaction.date
        state.save()

    return f"Categorized {transactions.count()} transactions for user {user.username}."