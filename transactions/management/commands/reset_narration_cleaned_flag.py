from django.core.management.base import BaseCommand
from transactions.models import Transaction

class Command(BaseCommand):
    help = 'Resets the narration_cleaned flag for all transactions'

    def handle(self, *args, **options):
        Transaction.objects.all().update(narration_cleaned=False)
        self.stdout.write(self.style.SUCCESS('Successfully reset narration_cleaned flag for all transactions.'))
