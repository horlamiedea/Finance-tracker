from django.core.management.base import BaseCommand
from transactions.models import ParserFunction

class Command(BaseCommand):
    help = 'Adds or updates the Kuda Bank V2 parser function.'

    def handle(self, *args, **options):
        parser_code = """
import re
from dateutil import parser as date_parser

def parse_email(soup):
    text = soup.get_text(separator=" ", strip=True)

    data = {
        "transaction_type": None,
        "amount": None,
        "date": None,
        "narration": None,
        "account_balance": None,
    }

    # Determine transaction type from keywords
    if "you sent" in text.lower() or "you spent" in text.lower():
        data["transaction_type"] = "debit"
    elif "you received" in text.lower():
        data["transaction_type"] = "credit"

    # Extract amount
    amount_match = re.search(r"(?:sent|spent|received)\\s+₦([\\d,]+\\.\\d{2})", text, re.IGNORECASE)
    if amount_match:
        data["amount"] = amount_match.group(1).replace(',', '')

    # Extract narration
    beneficiary_match = re.search(r"to\\s+([A-Za-z\\s\\d\\-\\_]+?)\\s+-", text)
    if beneficiary_match:
        beneficiary = beneficiary_match.group(1).strip()
        data["narration"] = f"Transfer to {beneficiary}"
    else:
        narration_match = re.search(r"at\\s+([A-Za-z\\s\\d\\-\\_]+?)\\.", text)
        if narration_match:
            narration = narration_match.group(1).strip()
            data["narration"] = f"Purchase at {narration}"

    # Extract date
    date_match = re.search(r"on\\s+([A-Za-z]+\\s+\\d{1,2},\\s+\\d{4})", text)
    if date_match:
        try:
            parsed_date = date_parser.parse(date_match.group(1))
            data["date"] = parsed_date.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            data["date"] = None
    
    # Extract account balance
    balance_match = re.search(r"new account balance is\\s+₦([\\d,]+\\.\\d{2})", text, re.IGNORECASE)
    if balance_match:
        data["account_balance"] = balance_match.group(1).replace(',', '')

    # If essential data is missing, it might not be a valid transaction email
    if not data["amount"] or not data["transaction_type"]:
        return None

    return data
"""
        
        parser_function, created = ParserFunction.objects.update_or_create(
            bank_name="Kuda Bank V2",
            defaults={'parser_code': parser_code}
        )

        if created:
            self.stdout.write(self.style.SUCCESS('Successfully created Kuda Bank V2 parser.'))
        else:
            self.stdout.write(self.style.SUCCESS('Successfully updated Kuda Bank V2 parser.'))
