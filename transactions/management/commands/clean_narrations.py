from django.core.management.base import BaseCommand
from transactions.models import Transaction
import re

class Command(BaseCommand):
    help = 'Cleans the narration field for all transactions'

    def handle(self, *args, **options):
        transactions = Transaction.objects.filter(narration_cleaned=False)
        for transaction in transactions:
            cleaned_narration = self.clean_narration(transaction.narration)
            transaction.narration = cleaned_narration
            transaction.narration_cleaned = True
            transaction.save()
        self.stdout.write(self.style.SUCCESS('Successfully cleaned narrations.'))

    def clean_narration(self, narration):
        patterns = [
            r'Narration:\s*(.*?)(?:\n\n|If you experience|Account Balance:|$)',
            r'Narrative\s*(.*?)Time',
            r'Note:\s*(.*?)(?:\n\n|Account Balance:|$)',
            r'Description:\s*(.*?)(?:\n\n|Account Balance:|$)',
            r'Details:\s*(.*?)(?:\n\n|Account Balance:|$)',
        ]

        for pattern in patterns:
            match = re.search(pattern, narration, re.IGNORECASE | re.DOTALL)
            if match:
                cleaned = match.group(1).strip()
                # Replace multiple spaces/newlines with a single space
                return ' '.join(cleaned.split())

        return narration
