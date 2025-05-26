import base64
import re
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from dateutil import parser as date_parser
import os
from openai import OpenAI
import json

client = OpenAI()

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

            raw_date = date_match.group(1).replace('|', ' ')
            transaction_date = date_parser.parse(raw_date)

            narration = narration_match.group(1).strip() if narration_match else 'N/A'

            return {
                'user_id': user.id, 
                'transaction_type': transaction_type,
                'amount': float(amount_str),
                'account_balance': account_balance,
                'date': transaction_date.isoformat(), 
                'narration': narration,
            }
        return None
    
    def debug_print_email_snippet(self, email_text, max_length=500):
        snippet = email_text[:max_length].replace('\n', ' ').replace('\r', ' ')
        print(f"Email snippet (first {max_length} chars): {snippet}")


    async def ai_parse_transaction_async(self, email_text):
        prompt = f"""
    You are an assistant that extracts banking transaction information from email text.

    Given the email content below, extract the following details:

    - transaction_type: "debit" or "credit" (or "none" if not a transaction)
    - amount: numeric string (e.g., "5480.00")
    - date: transaction date and time in ISO 8601 format (YYYY-MM-DDTHH:MM:SS)
    - narration: short description of the transaction
    - account_balance: numeric string if available, else null

    If the email does not contain a transaction, return {{"transaction_type": "none"}}.

    Return ONLY a valid JSON object without any extra text, comments, or explanations.
    The JSON must be parsable by standard JSON parsers.

    Email content:
    \"\"\"
    {email_text}
    \"\"\"
    """
        import asyncio
        from functools import partial

        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            partial(
                client.chat.completions.create,
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=256,
                temperature=0
            )
        )
        
        raw_content = response.choices[0].message.content
        print("Raw OpenAI response content:")
        print(raw_content)

        import json
        try:
            parsed_json = json.loads(raw_content)
            return parsed_json
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            return {"transaction_type": "none"}