from django.core.management.base import BaseCommand
from transactions.models import TransactionCategory

DEFAULT_CATEGORIES = [
    "Family",
    "Black Tax",
    "Utility Bill",
    "Feeding",
    "Hospital Bill",
    "Fuel",
    "Savings",
    "Transportation",
    "Shopping",
    "Entertainment",
    "Education",
    "Rent",
    "Subscription",
    "Investment",
    "Unknown"
]

class Command(BaseCommand):
    help = "Load default transaction categories into the database."

    def handle(self, *args, **kwargs):
        for cat_name in DEFAULT_CATEGORIES:
            category, created = TransactionCategory.objects.get_or_create(name=cat_name)
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created category: {cat_name}"))
            else:
                self.stdout.write(f"Category already exists: {cat_name}")
