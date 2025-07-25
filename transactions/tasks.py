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
from .html_parser import HTMLParserService
from .models import RawEmail
from django.db.models import Q
from transactions.models import TransactionCategory
from receipts.models import Receipt

logger = logging.getLogger(__name__)
User = get_user_model()
client = OpenAI(api_key=settings.OPENAI_API_KEY)


@shared_task(max_retries=2, default_retry_delay=60)
def process_raw_email_task(raw_email_id: int):
    """
    Processes a raw email using an advanced, self-improving tiered approach
    with a final data recovery step for incomplete parses.
    """
    try:
        raw_email = RawEmail.objects.get(id=raw_email_id)
    except RawEmail.DoesNotExist:
        logger.error(f"RawEmail with ID {raw_email_id} not found.")
        return

    if raw_email.parsed:
        return

    html_parser = HTMLParserService()
    ai_service = AIService()
    parsed_data = None
    parsing_method_used = 'none'

    # --- Step 1 & 2: Attempt parsing with saved functions or generate a new one ---
    parsed_data = html_parser.run_all_parsers(raw_email.raw_text)
    if parsed_data:
        parsing_method_used = 'dynamic_html_parser_success'
    else:
        bank_name = html_parser.get_bank_name_from_html(raw_email.raw_text)
        if bank_name and bank_name != 'Unknown':
            new_parser_code = ai_service.generate_parser_function(raw_email.raw_text)
            if new_parser_code:
                parsed_data = html_parser.run_single_parser(new_parser_code, raw_email.raw_text)
                if parsed_data:
                    ParserFunction.objects.update_or_create(bank_name=bank_name, defaults={'parser_code': new_parser_code})
                    parsing_method_used = 'ai_generated_parser_success'
    
    # --- Step 3: Final fallback to direct AI extraction ---
    if not parsed_data:
        parsed_data = ai_service.extract_transaction_from_email(raw_email.raw_text)
        if parsed_data:
            parsing_method_used = 'ai_fallback_success'

    # --- Step 4: Validate and Process the Data ---
    if not parsed_data:
        raw_email.parsed = True
        raw_email.parsing_method = 'all_methods_failed'
        raw_email.save()
        logger.critical(f"CRITICAL: All parsing methods failed for RawEmail ID {raw_email.id}. Manual review required.")
        return

    # --- Step 5: Data Recovery for Incomplete Parses ---
    is_data_complete = all(parsed_data.get(key) for key in ['amount', 'date', 'transaction_type', 'narration'])
    if not is_data_complete and parsed_data.get('narration'):
        logger.warning(f"Initial parse for RawEmail {raw_email.id} is incomplete. Attempting data recovery...")
        recovered_data = ai_service.recover_missing_data_from_text(parsed_data['narration'])
        if recovered_data:
            # Update the original parsed_data with any fields the recovery found
            # This uses the recovered value only if the original was missing.
            for key, value in recovered_data.items():
                if not parsed_data.get(key) and value is not None:
                    parsed_data[key] = value
            logger.info(f"Successfully recovered data for RawEmail {raw_email.id}.")

    # --- Step 6: Handle Non-Transactional Emails ---
    narration_lower = (parsed_data.get('narration') or "").lower()
    non_transactional_keywords = ['log in confirmation', 'security alert', 'password reset', 'welcome back']
    if any(keyword in narration_lower for keyword in non_transactional_keywords):
        logger.info(f"Detected and deleting non-transactional email (ID: {raw_email.id})")
        raw_email.delete()
        return

    # --- Step 7: Final Validation and Transaction Creation ---
    try:
        amount_str = (parsed_data.get('amount') or '0').replace(',', '')
        amount = Decimal(amount_str)
        date_str = parsed_data.get('date')
        trans_type = parsed_data.get('transaction_type')
        narration = parsed_data.get('narration')

        if not all([amount_str, date_str, trans_type, narration]):
             raise ValueError("Essential data (amount, date, type, or narration) is missing even after recovery.")

        trans_date = date_parser.parse(date_str)
        
        transaction, created = Transaction.objects.get_or_create(
            user=raw_email.user, amount=amount, date=trans_date, transaction_type=trans_type, narration=narration,
            defaults={
                'bank_name': parsed_data.get('bank_name'),
                'account_balance': Decimal(str(parsed_data.get('account_balance')).replace(',', '')) if parsed_data.get('account_balance') else None,
            }
        )

        raw_email.parsed = True
        raw_email.parsing_method = parsing_method_used
        raw_email.transaction_data = parsed_data
        raw_email.save()

        if created:
            logger.info(f"Successfully created transaction for RawEmail {raw_email.id} using {parsing_method_used}.")
        else:
            logger.info(f"Transaction from RawEmail {raw_email.id} already exists.")

    except (ValueError, InvalidOperation, TypeError) as e:
        logger.error(f"Final data validation or type error for RawEmail {raw_email.id}. Error: {e}, Data: {parsed_data}")
        raw_email.parsing_method = 'creation_failed_data_error'
        raw_email.transaction_data = parsed_data
        raw_email.save()


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
            process_raw_email_task.delay(raw_email.id)
            email_count += 1

    logger.info(f"Found {len(emails)} total emails, initiating processing for {email_count} new emails for user {user.username}.")
    return f"Initiated processing for {email_count} new emails for user {user.username}."

@shared_task
def categorize_transactions_for_user(user_id):
    """
    A robust task to categorize a user's transactions using a multi-step process:
    1. Similarity check against already categorized transactions.
    2. AI-powered categorization with few-shot learning from the user's history.
    """
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error(f"Categorization task failed: User with id {user_id} not found.")
        return

    # Fetch all uncategorized transactions for the user
    transactions_to_process = Transaction.objects.filter(
        user=user,
        category__isnull=True
    ).order_by('date')

    if not transactions_to_process.exists():
        logger.info(f"No new transactions to categorize for user {user.username}")
        return "No new transactions to categorize."

    # --- Prepare data for categorization ---
    
    # 1. Get all possible category names
    all_categories = list(TransactionCategory.objects.values_list('name', flat=True))
    if not all_categories:
        logger.warning(f"Cannot categorize for user {user.username}: No TransactionCategory records exist.")
        return "No categories available to assign."

    # 2. Get all of the user's *already categorized* transactions for learning
    # We convert to a list to dynamically add new categorizations during the run
    categorized_transactions = list(Transaction.objects.filter(
        user=user,
        category__isnull=False
    ).exclude(category__name="Unknown").values('narration', 'category__name'))

    # 3. Initialize the AI service
    ai_service = AIService()
    
    processed_count = 0
    for tx in transactions_to_process:
        narration_lower = tx.narration.lower()
        matched_category_name = None

        # --- Step 1: Fast Similarity Check (difflib) ---
        # Find the best match among existing transactions if similarity is high.
        if categorized_transactions:
            # Create a simple function to calculate similarity
            def get_similarity(item):
                return difflib.SequenceMatcher(None, narration_lower, item['narration'].lower()).ratio()

            best_match = max(categorized_transactions, key=get_similarity)
            similarity_score = get_similarity(best_match)

            if similarity_score > 0.85: # Using a slightly higher threshold for confidence
                matched_category_name = best_match['category__name']
                logger.info(f"Categorized tx {tx.id} as '{matched_category_name}' via similarity match (score: {similarity_score:.2f})")

        # --- Step 2: AI-Powered Categorization (if no high-similarity match) ---
        if not matched_category_name:
            # Provide recent, relevant examples for the AI to learn from
            ai_examples = categorized_transactions[-10:] # Use last 10 as examples
            
            logger.info(f"Using AI to categorize transaction {tx.id}...")
            matched_category_name = ai_service.categorize_transaction(
                narration=tx.narration,
                categories=all_categories,
                examples=ai_examples
            )
            logger.info(f"AI categorized tx {tx.id} as '{matched_category_name}'")

        # --- Step 3: Assign the Category ---
        if matched_category_name:
            try:
                # Get or create to be safe, though it should exist from `all_categories`
                category_obj, _ = TransactionCategory.objects.get_or_create(name=matched_category_name)
                tx.category = category_obj
                tx.save()
                
                # Only count non-"Unknown" as successfully processed
                if matched_category_name != "Unknown":
                    processed_count += 1
                    # Add this newly categorized transaction to our list for the next iteration in this run
                    # This helps the model learn from its own recent decisions within the same batch
                    categorized_transactions.append({'narration': tx.narration, 'category__name': matched_category_name})

            except Exception as e:
                logger.error(f"Could not assign category '{matched_category_name}' to transaction {tx.id}. Error: {e}")

    return f"Categorized {processed_count} transactions for user {user.username}."


@shared_task
def reconcile_similar_transactions_task(transaction_id):
    """
    Triggered after a user manually changes a transaction's category.
    This task finds transactions with similar narrations and updates their
    category to match the user's correction, effectively 'learning' from it.
    """
    try:
        source_transaction = Transaction.objects.get(id=transaction_id)
    except Transaction.DoesNotExist:
        logger.error(f"Reconciliation task failed: Transaction {transaction_id} not found.")
        return

    user = source_transaction.user
    correct_category = source_transaction.category
    source_narration = source_transaction.narration.lower()

    # If the user sets the category to null, we don't propagate this change.
    if not correct_category:
        logger.info(f"Reconciliation skipped: Category for Tx {transaction_id} was set to null.")
        return

    # Find other transactions from the same user that are NOT in the correct category yet.
    # This includes uncategorized transactions or those with a different category.
    candidate_transactions = Transaction.objects.filter(
        user=user
    ).exclude(
        id=transaction_id
    ).exclude(
        category=correct_category
    )

    updated_count = 0
    for tx in candidate_transactions:
        # Use a high similarity ratio to be confident in the automatic change.
        similarity = difflib.SequenceMatcher(None, source_narration, tx.narration.lower()).ratio()
        
        if similarity > 0.85:
            logger.info(f"Reconciling Tx {tx.id} based on user correction for Tx {source_transaction.id}. New category: '{correct_category.name}'.")
            tx.category = correct_category
            tx.is_manually_categorized = False # This change is automatic, not manual.
            tx.save(update_fields=['category', 'is_manually_categorized'])
            updated_count += 1
            
    logger.info(f"Reconciled and updated {updated_count} transactions based on user correction for Tx {transaction_id}.")
    return f"Reconciled {updated_count} transactions."



@shared_task
def reprocess_failed_emails_task(user_id):
    """
    Scans for emails that were fetched but failed to parse correctly
    and re-triggers the AI processing task for them.
    This acts as a manual "checker" for the user.
    """
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error(f"Reprocessing task failed: User with id {user_id} not found.")
        return

    # Find emails that are either un-parsed or marked as failed.
    failed_emails = RawEmail.objects.filter(
        Q(user=user) & 
        (Q(parsed=False) | Q(parsing_method__icontains='failed'))
    )
    
    count = failed_emails.count()
    if count == 0:
        logger.info(f"No failed emails to reprocess for user {user.username}.")
        return "No failed emails found to reprocess."

    logger.info(f"Found {count} failed emails to reprocess for user {user.username}. Triggering tasks...")

    for raw_email in failed_emails:
        # Reset the status to allow the processing task to run again.
        raw_email.parsed = False
        raw_email.parsing_method = 'none'
        raw_email.save()
        
        # Trigger the AI processing task.
        process_raw_email_task.delay(raw_email.id)

    return f"Initiated reprocessing for {count} failed emails."