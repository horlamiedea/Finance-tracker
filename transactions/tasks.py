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
import difflib
from openai import OpenAI
from dateutil import parser as date_parser
from .services.ai_service import AIService
from django.conf import settings
import logging
from decimal import InvalidOperation

logger = logging.getLogger(__name__)
User = get_user_model()
client = OpenAI(api_key=settings.OPENAI_API_KEY)

@shared_task(max_retries=3, default_retry_delay=60)
def process_email_with_ai(raw_email_id: int):
    """
    Takes a RawEmail ID, sends its content to the AI service for parsing,
    and creates a Transaction record. Retries on failure.
    This version includes robust error handling and status updates.
    """
    try:
        raw_email = RawEmail.objects.get(id=raw_email_id)
    except RawEmail.DoesNotExist:
        logger.error(f"RawEmail with ID {raw_email_id} not found.")
        return

    if raw_email.parsed:
        logger.info(f"RawEmail {raw_email.id} has already been parsed. Skipping.")
        return

    ai_service = AIService()
    parsed_data = ai_service.extract_transaction_from_email(raw_email.raw_text)

    if not parsed_data:
        raw_email.parsed = True
        raw_email.parsing_method = 'ai_failed'
        raw_email.save()
        logger.warning(f"AI service could not parse RawEmail ID {raw_email.id}")
        return

    # --- THE FIX: Defensive data validation ---
    # Use .get() to avoid KeyErrors and check for essential data before proceeding.
    amount_str = parsed_data.get('amount')
    date_str = parsed_data.get('date')
    trans_type = parsed_data.get('transaction_type')

    if not all([amount_str, date_str, trans_type]):
        raw_email.parsed = True
        raw_email.parsing_method = 'ai_missing_data'
        raw_email.transaction_data = parsed_data
        raw_email.save()
        logger.error(f"AI response for RawEmail {raw_email.id} was missing essential data (amount, date, or type). Data: {parsed_data}")
        return

    try:
        amount = Decimal(str(amount_str))
        trans_date = date_parser.parse(date_str)
        
        transaction, created = Transaction.objects.get_or_create(
            user=raw_email.user,
            amount=amount,
            date=trans_date,
            transaction_type=trans_type,
            defaults={
                'narration': parsed_data.get('narration', 'N/A'),
                'bank_name': parsed_data.get('bank_name'),
                'account_balance': Decimal(str(parsed_data.get('account_balance'))) if parsed_data.get('account_balance') else None,
            }
        )

        if created:
            logger.info(f"Successfully created transaction from RawEmail {raw_email.id}")
        else:
            logger.info(f"Transaction from RawEmail {raw_email.id} already exists.")

        raw_email.parsed = True
        raw_email.parsing_method = 'ai_success'
        raw_email.transaction_data = parsed_data
        raw_email.save()

    except (InvalidOperation, ValueError, TypeError) as e:
        logger.error(f"Data type conversion error for RawEmail {raw_email.id}. Error: {e}, Data: {parsed_data}")
        raw_email.parsing_method = 'creation_failed_data_error'
        raw_email.transaction_data = parsed_data
        raw_email.save()
    except Exception as e:
        logger.error(f"An unexpected error occurred creating transaction for RawEmail {raw_email.id}. Error: {e}, Data: {parsed_data}")
        raw_email.parsing_method = 'creation_failed_unknown'
        raw_email.transaction_data = parsed_data
        raw_email.save()


@shared_task
def sync_user_transactions_task(user_id, start_date_iso, end_date_iso):
    """
    Fetches emails for a user, saves them to the RawEmail model,
    and triggers the AI processing task for each new email.
    """
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error(f"sync_user_transactions_task: User {user_id} not found.")
        return

    credentials_dict = {
        "token": user.gmail_token,
        "refresh_token": user.gmail_refresh_token,
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    
    if not all(c for c in [user.gmail_token, user.gmail_refresh_token]):
        logger.error(f"Missing Gmail OAuth credentials for user {user_id}")
        return

    gmail_service = GmailService(credentials_dict)
    
    bank_domains = [
        "providusbank.com", "moniepoint.com", "opay-nigeria.com",
        "uba.com", "gtbank.com", "zenithbank.com", "accessbankplc.com",
        "firstbanknigeria.com", "wemabank.com", "alat.ng", "kudabank.com"
    ]
    from_query = " OR ".join([f"from:{domain}" for domain in bank_domains])
    
    query = f"after:{start_date_iso.split('T')[0]} before:{end_date_iso.split('T')[0]} {{ {from_query} }}"

    logger.info(f"Using Gmail query: {query}")

    try:
        emails = gmail_service.fetch_emails(query=query)
    except Exception as e:
        logger.error(f"Failed to fetch emails for user {user_id}: {e}")
        return

    email_count = 0
    for email_details in emails:
        email_body = email_details['body']
        message_id = email_details['id']

        if not RawEmail.objects.filter(user=user, email_id=message_id).exists():
            raw_email = RawEmail.objects.create(
                user=user,
                email_id=message_id,
                raw_text=email_body,
                parsing_method='none'
            )
            process_email_with_ai.delay(raw_email.id)
            email_count += 1

    logger.info(f"Found {len(emails)} total emails, initiating processing for {email_count} new emails for user {user.username}.")
    return f"Initiated processing for {email_count} new emails for user {user.username}."

@shared_task
def categorize_transactions_for_user(user_id):
    user = User.objects.get(id=user_id)
    state, created = UserTransactionCategorizationState.objects.get_or_create(user=user)
    last_processed = state.last_processed_date or '1970-01-01T00:00:00Z'

    # Fetch uncategorized transactions newer than last_processed_date
    transactions = Transaction.objects.filter(
        user=user,
        date__gt=last_processed,
        category__isnull=True
    ).order_by('date')

    # If no new uncategorized transactions, fetch all "Unknown" transactions
    if not transactions.exists():
        transactions = Transaction.objects.filter(
            user=user,
            category__name="Unknown"
        ).order_by('date')
        if not transactions.exists():
            logger.info(f"No new or Unknown transactions to categorize for user {user.username}")
            return "No new or Unknown transactions to categorize."

    # Fetch all categories from DB
    categories = list(TransactionCategory.objects.values_list('name', flat=True))

    # User keyword mappings
    user_mappings = UserCategoryMapping.objects.filter(user=user)
    user_keyword_map = {}
    for mapping in user_mappings:
        for keyword in mapping.keywords:
            user_keyword_map[keyword.lower()] = mapping.transaction_category.name

    # Fetch all categorized transactions (excluding "Unknown") for similarity checks
    categorized_transactions = Transaction.objects.filter(
        user=user,
        category__isnull=False
    ).exclude(category__name="Unknown").values('narration', 'category__name')

    processed_count = 0
    for tx in transactions:
        narration_lower = tx.narration.lower()
        matched_category = None

        # Step 1: Check user-defined keywords
        for keyword, cat_name in user_keyword_map.items():
            if keyword in narration_lower:
                matched_category = TransactionCategory.objects.get(name=cat_name)
                break

        # Step 2: Check for similar categorized transactions
        if not matched_category:
            for cat_tx in categorized_transactions:
                similarity = difflib.SequenceMatcher(None, narration_lower, cat_tx['narration'].lower()).ratio()
                if similarity > 0.8:  # Adjustable similarity threshold
                    matched_category = TransactionCategory.objects.get(name=cat_tx['category__name'])
                    break

        # Step 3: If no match yet, use AI categorization
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
                if category_name in categories:
                    matched_category, _ = TransactionCategory.objects.get_or_create(name=category_name)
                else:
                    matched_category, _ = TransactionCategory.objects.get_or_create(name="Unknown")
            except Exception as e:
                logger.error(f"OpenAI API error for user {user.username} transaction {tx.id}: {e}")
                matched_category, _ = TransactionCategory.objects.get_or_create(name="Unknown")

        # Assign the category to the transaction
        if matched_category:
            tx.category = matched_category
            tx.save()
            processed_count += 1
            logger.info(f"Categorized transaction {tx.id} as {matched_category.name}")

        # Update purchase frequency for receipt items
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

    # Update last processed date only if new transactions were processed
    if transactions.filter(date__gt=last_processed).exists():
        last_transaction = transactions.filter(date__gt=last_processed).last()
        if last_transaction:
            state.last_processed_date = last_transaction.date
            state.save()

    return f"Categorized {processed_count} transactions for user {user.username}."