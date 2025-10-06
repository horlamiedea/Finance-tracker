from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from transactions.models import Transaction, Bank

class Command(BaseCommand):
    help = 'Populates the Bank table with unique bank names from the Transaction table for each user.'

    def handle(self, *args, **options):
        User = get_user_model()
        users = User.objects.all()

        for user in users:
            bank_names = Transaction.objects.filter(user=user).values_list('bank_name', flat=True).distinct()
            
            for name in bank_names:
                if name:
                    bank, created = Bank.objects.get_or_create(user=user, name=name)
                    if created:
                        self.stdout.write(self.style.SUCCESS(f'Successfully created bank "{name}" for user {user.username}'))
                    else:
                        self.stdout.write(self.style.WARNING(f'Bank "{name}" already exists for user {user.username}'))
