import base64
import re
from google.oauth2.credentials import Credentials

from googleapiclient.discovery import build
from dateutil import parser as date_parser
import os
from openai import OpenAI
from django.conf import settings
from asgiref.sync import sync_to_async
import asyncio
import pytz
import json
import logging
from bs4 import BeautifulSoup
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

client = OpenAI()

class GmailService:
    def __init__(self, credentials_dict):
        """Initializes the Gmail Service client."""
        self.creds = Credentials(
            token=credentials_dict.get('token'),
            refresh_token=credentials_dict.get('refresh_token'),
            token_uri=credentials_dict.get('token_uri'),
            client_id=credentials_dict.get('client_id'),
            client_secret=credentials_dict.get('client_secret'),
        )
        self.service = build('gmail', 'v1', credentials=self.creds)

    def fetch_emails(self, query=''):
        """
        THE FIX: Fetches all messages within conversation threads matching the query.
        This is more robust and prevents missing 'stacked' emails.
        """
        all_messages = []
        try:
            # First, get all threads that match the query
            threads_response = self.service.users().threads().list(userId='me', q=query).execute()
            threads = threads_response.get('threads', [])
            
            for thread_info in threads:
                # For each thread, get all of its messages
                thread_details = self.service.users().threads().get(userId='me', id=thread_info['id']).execute()
                messages_in_thread = thread_details.get('messages', [])
                for message_info in messages_in_thread:
                    # Get the full details for each message
                    all_messages.append(self.get_email_details(message_info['id']))

            logger.info(f"Found {len(all_messages)} messages across {len(threads)} threads.")
            return all_messages
            
        except HttpError as error:
            logger.error(f"An HTTP error occurred while fetching email threads: {error}")
            return []
        except Exception as e:
            logger.error(f"An unexpected error occurred while fetching email threads: {e}")
            return []

    def get_email_details(self, msg_id: str) -> dict:
        try:
            message = self.service.users().messages().get(userId='me', id=msg_id, format='full').execute()
            payload = message.get('payload', {})
            headers = payload.get('headers', [])
            parts = payload.get('parts', [])
            data = None

            if parts:
                for part in parts:
                    if part.get('mimeType') == 'text/html' and part.get('body') and part['body'].get('data'):
                        data = part['body']['data']
                        break
                    elif part.get('parts'):
                        for subpart in part['parts']:
                            if subpart.get('mimeType') == 'text/html' and subpart.get('body') and subpart['body'].get('data'):
                                data = subpart['body']['data']
                                break
                        if data:
                            break
            elif payload.get('body'):
                data = payload['body'].get('data')

            email_text = ''
            if data:
                email_text = base64.urlsafe_b64decode(data).decode(errors='ignore')

            # Extract sent date from headers and make it timezone-aware
            sent_date_str = next((h['value'] for h in headers if h['name'].lower() == 'date'), None)
            sent_date = None
            if sent_date_str:
                try:
                    sent_date = date_parser.parse(sent_date_str)
                    if sent_date.tzinfo is None:
                        sent_date = sent_date.replace(tzinfo=pytz.UTC)
                except ValueError:
                    logger.warning(f"Could not parse sent date: {sent_date_str}")

            return {'id': msg_id, 'body': email_text, 'headers': headers, 'sent_date': sent_date}

        except HttpError as error:
            logger.error(f"An HTTP error occurred getting details for message {msg_id}: {error}")
        except Exception as e:
            logger.error(f"An unexpected error occurred getting details for message {msg_id}: {e}")
        return {'id': msg_id, 'body': '', 'headers': [], 'sent_date': None}

    def get_bank_name(self, headers):
        from_header = next((h['value'] for h in headers if h['name'].lower() == 'from'), '')
        subject_header = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '')

        domain_match = re.search(r'@([a-zA-Z0-9\-]+)\.(com|ng)', from_header)
        if domain_match:
            domain = domain_match.group(1).lower()
            bank_name_map = {
                'providusbank': 'Providus Bank',
                'opay-nigeria': 'Opay',
                'alat': 'Alat',
                'wemabank': 'Wema Bank',
                'uba': 'UBA Bank',
                'zenithbank': 'Zenith Bank',
                'moniepoint': 'Moniepoint',  # Added for your example
            }
            bank_name = bank_name_map.get(domain)
            if bank_name:
                return bank_name
            return ' '.join(word.capitalize() for word in domain.split('-'))

        # Fallback to subject line
        subject_lower = subject_header.lower()
        if 'providusbank' in subject_lower:
            return 'Providus Bank'
        elif 'opay' in subject_lower:
            return 'Opay'
        elif 'alat' in subject_lower:
            return 'Alat'
        elif 'moniepoint' in subject_lower:
            return 'Moniepoint'
        return 'Unknown'

    def parse_transaction(self, email_text, bank_name):
        """Parse transaction details using BeautifulSoup."""
        try:
            soup = BeautifulSoup(email_text, 'html.parser')
            transaction_data = {'transaction_type': 'none', 'bank_name': bank_name}

            if bank_name == 'Providus Bank':
                table = soup.find('table', {'width': '690px'}) or soup.find('table')
                if table:
                    rows = table.find_all('tr')
                    for i, row in enumerate(rows):
                        cells = row.find_all('td')
                        if len(cells) < 2:
                            continue
                        key = cells[0].get_text(strip=True).lower()
                        value = cells[1].get_text(strip=True)
                        if 'account number' in key:
                            transaction_data['account_number'] = value
                        elif 'amount' in key:
                            amount_match = re.search(r'NGN\s*([\d,]+\.\d{2})', value)
                            if amount_match:
                                transaction_data['amount'] = amount_match.group(1).replace(',', '')
                            transaction_data['transaction_type'] = 'debit' if 'Debit' in soup.get_text() else 'credit'
                        elif 'narrative' in key:
                            transaction_data['narration'] = value
                        elif 'time' in key:
                            try:
                                transaction_data['date'] = date_parser.parse(value).isoformat()
                            except ValueError:
                                transaction_data['date'] = None
                        elif 'available balance' in key:
                            balance_match = re.search(r'NGN\s*([\d,]+\.\d{2})', value)
                            if balance_match:
                                transaction_data['account_balance'] = balance_match.group(1).replace(',', '')

            elif bank_name == 'Opay':
                amount_span = soup.find('span', text=re.compile(r'₦[\d,]+\.\d{2}'))
                if amount_span:
                    amount_match = re.search(r'([\d,]+\.\d{2})', amount_span.get_text())
                    if amount_match:
                        transaction_data['amount'] = amount_match.group(1).replace(',', '')
                    transaction_data['transaction_type'] = 'debit' if 'transfer' in soup.get_text().lower() else 'credit'
                balance_span = soup.find('span', text=re.compile(r'₦[\d,]+\.\d{2}'))
                if balance_span and 'available balance' in soup.get_text().lower():
                    balance_match = re.search(r'([\d,]+\.\d{2})', balance_span.get_text())
                    if balance_match:
                        transaction_data['account_balance'] = balance_match.group(1).replace(',', '')
                date_span = soup.find('span', text=re.compile(r'\w+\s+\d{1,2}(?:th|st|nd|rd),\s+\d{4}\s+\d{2}:\d{2}:\d{2}'))
                if date_span:
                    try:
                        transaction_data['date'] = date_parser.parse(date_span.get_text()).isoformat()
                    except ValueError:
                        transaction_data['date'] = None
                narration_span = soup.find('span', text=re.compile(r'816\d{7}'))
                if narration_span:
                    transaction_data['narration'] = f"Transfer to {narration_span.get_text()}"

            elif bank_name == 'Alat':
                amount_text = soup.find('span', text=re.compile(r'NGN\s+[\d,]+\.\d{2}'))
                if amount_text:
                    amount_match = re.search(r'([\d,]+\.\d{2})', amount_text.get_text())
                    if amount_match:
                        transaction_data['amount'] = amount_match.group(1).replace(',', '')
                    transaction_data['transaction_type'] = 'credit' if 'credited' in soup.get_text().lower() else 'debit'
                balance_row = soup.find('td', text=re.compile(r'Account Balance'))
                if balance_row:
                    balance_cell = balance_row.find_next_sibling('td')
                    balance_match = re.search(r'([\d,]+\.\d{2})', balance_cell.get_text())
                    if balance_match:
                        transaction_data['account_balance'] = balance_match.group(1).replace(',', '')
                date_row = soup.find('td', text=re.compile(r'Date and Time'))
                if date_row:
                    date_cell = date_row.find_next_sibling('td')
                    try:
                        transaction_data['date'] = date_parser.parse(date_cell.get_text()).isoformat()
                    except ValueError:
                        transaction_data['date'] = None
                note_row = soup.find('td', text=re.compile(r'Note'))
                if note_row:
                    transaction_data['narration'] = note_row.find_next_sibling('td').get_text(strip=True)

            else:
                amount_match = re.search(r'(?:NGN|₦)\s*([\d,]+\.\d{2})', soup.get_text())
                if amount_match:
                    transaction_data['amount'] = amount_match.group(1).replace(',', '')
                    transaction_data['transaction_type'] = 'debit' if 'debit' in soup.get_text().lower() else 'credit'
                balance_match = re.search(r'(?:Balance|Available Balance).*?(?:NGN|₦)\s*([\d,]+\.\d{2})', soup.get_text(), re.IGNORECASE)
                if balance_match:
                    transaction_data['account_balance'] = balance_match.group(1).replace(',', '')
                date_match = re.search(r'\d{1,2}[-/]\d{1,2}[-/]\d{4}\s+\d{2}:\d{2}:\d{2}|\w+\s+\d{1,2}(?:th|st|nd|rd),\s+\d{4}\s+\d{2}:\d{2}:\d{2}', soup.get_text())
                if date_match:
                    try:
                        transaction_data['date'] = date_parser.parse(date_match.group(0)).isoformat()
                    except ValueError:
                        transaction_data['date'] = None
                narration_match = re.search(r'(?:Narration|Narrative|Note|Description):?\s*(.+?)(?=\n|\s{2,}|$)', soup.get_text(), re.IGNORECASE)
                if narration_match:
                    transaction_data['narration'] = narration_match.group(1).strip()

            if transaction_data.get('amount') and transaction_data.get('date') and transaction_data.get('transaction_type') != 'none':
                return transaction_data
            return {'transaction_type': 'none', 'bank_name': bank_name}
        except Exception as e:
            logger.error(f"Error parsing email for bank {bank_name}: {str(e)}")
            return {'transaction_type': 'none', 'bank_name': bank_name}

    def debug_print_email_snippet(self, email_text, max_length=500):
        snippet = email_text[:max_length].replace('\n', ' ').replace('\r', ' ')
        logger.info(f"Email snippet (first {max_length} chars): {snippet}")