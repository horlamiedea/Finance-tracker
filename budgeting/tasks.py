from celery import shared_task
from django.contrib.auth import get_user_model
from budgeting.services import analyze_spending_frequency

User = get_user_model()

@shared_task
def update_spending_frequency():
    for user in User.objects.all():
        analyze_spending_frequency(user)
