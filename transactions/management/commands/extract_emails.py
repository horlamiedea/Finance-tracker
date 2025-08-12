from django.core.management.base import BaseCommand
from transactions.models import RawEmail
from transactions.tasks import process_raw_email_task
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    help = "Batch extract and process all unparsed or failed emails for all users (or a specific user)."

    def add_arguments(self, parser):
        parser.add_argument('--user', type=str, help='Username or email of the user to process (optional)')

    def handle(self, *args, **options):
        user_filter = {}
        if options['user']:
            User = get_user_model()
            try:
                user = User.objects.get(username=options['user'])
            except User.DoesNotExist:
                try:
                    user = User.objects.get(email=options['user'])
                except User.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f"User '{options['user']}' not found."))
                    return
            user_filter = {'user': user}

        # Find all unparsed or failed emails
        emails = RawEmail.objects.filter(
            parsed=False
        ).filter(**user_filter) | RawEmail.objects.filter(
            parsing_method__icontains='failed'
        ).filter(**user_filter)

        emails = emails.distinct()
        total = emails.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS("No unparsed or failed emails found."))
            return

        self.stdout.write(f"Found {total} unparsed or failed emails. Processing...")

        for raw_email in emails:
            process_raw_email_task(raw_email.id)
            self.stdout.write(f"Processed RawEmail ID {raw_email.id} for user {raw_email.user}")

        self.stdout.write(self.style.SUCCESS("Batch extraction and processing complete."))
