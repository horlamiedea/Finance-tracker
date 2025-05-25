import base64
import re
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from dateutil import parser as date_parser

class GmailService:
    def __init__(self, credentials_dict):
        self.creds = Credentials(
            token=credentials_dict.get('token'),
            refresh_token=credentials_dict.get('refresh_token'),
            token_uri=credentials_dict.get('token_uri'),
            client_id=credentials_dict.get('client_id'),
            client_secret=credentials_dict.get('client_secret'),
        )
        self.service = build('gmail', 'v1', credentials=self.creds)

    def fetch_emails(self, query=''):
        results = self.service.users().messages().list(userId='me', q=query).execute()
        messages = results.get('messages', [])
        return [self.get_email_details(m['id']) for m in messages]

    def get_email_details(self, msg_id):
        message = self.service.users().messages().get(userId='me', id=msg_id).execute()
        payload = message['payload']
        parts = payload.get('parts', [])
        data = None
        if parts:
            # sometimes message body is nested in parts
            for part in parts:
                if part.get('body') and part['body'].get('data'):
                    data = part['body']['data']
                    break
        else:
            data = payload['body'].get('data')

        if not data:
            return ''

        email_text = base64.urlsafe_b64decode(data).decode(errors='ignore')
        return email_text


    def parse_transaction(self, email_text, user):
        amount_match = re.search(r'(Debit|Credit) Amount\s+([\d,]+\.\d{2})', email_text, re.IGNORECASE)
        balance_match = re.search(r'Account Balance:\s*N\s*([\d,]+\.\d{2})', email_text, re.IGNORECASE)
        date_match = re.search(r'Date & Time:\s*([\d]{1,2} [A-Za-z]+, [\d]{4} \| [\d:]+ [AP]M)', email_text, re.IGNORECASE)
        narration_match = re.search(r'Narration:\s*(.+)', email_text, re.IGNORECASE)

        if amount_match and date_match:
            transaction_type = amount_match.group(1).lower()
            amount_str = amount_match.group(2).replace(',', '')
            account_balance = float(balance_match.group(1).replace(',', '')) if balance_match else None

            # Fix date parsing by removing the pipe '|'
            raw_date = date_match.group(1).replace('|', ' ')
            transaction_date = date_parser.parse(raw_date)

            narration = narration_match.group(1).strip() if narration_match else 'N/A'

            return {
                'user': user,
                'transaction_type': transaction_type,
                'amount': float(amount_str),
                'account_balance': account_balance,
                'date': transaction_date,
                'narration': narration,
            }
        return None
    
    def debug_print_email_snippet(self, email_text, max_length=500):
        snippet = email_text[:max_length].replace('\n', ' ').replace('\r', ' ')
        print(f"Email snippet (first {max_length} chars): {snippet}")
