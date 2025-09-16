from datetime import timedelta
from django.utils import timezone
from transactions.models import Transaction
from budgeting.models import TransactionFrequency, ItemFrequency
from collections import defaultdict

def analyze_spending_frequency(user):
    analyze_transaction_frequency(user)
    analyze_item_frequency(user)

def analyze_transaction_frequency(user):
    transactions = Transaction.objects.filter(user=user, transaction_type='debit').order_by('date')
    narration_groups = defaultdict(list)

    for t in transactions:
        narration_groups[t.narration].append(t.date)

    for narration, dates in narration_groups.items():
        if len(dates) > 1:
            frequency = calculate_frequency(dates)
            if frequency:
                transaction_count = len(dates)
                last_transaction_date = dates[-1]
                next_predicted_date = predict_next_date(last_transaction_date, frequency)
                
                TransactionFrequency.objects.update_or_create(
                    user=user,
                    narration=narration,
                    defaults={
                        'frequency': frequency,
                        'transaction_count': transaction_count,
                        'last_transaction_date': last_transaction_date,
                        'next_predicted_date': next_predicted_date,
                        'confidence_score': 0.8 # Placeholder
                    }
                )

def analyze_item_frequency(user):
    transactions = Transaction.objects.filter(user=user, receipt_items__isnull=False).order_by('date')
    item_groups = defaultdict(lambda: defaultdict(list))

    for t in transactions:
        if isinstance(t.receipt_items, list):
            for item in t.receipt_items:
                description = item.get('description')
                if description:
                    item_groups[description][t.category].append(t.date)

    for description, category_dates in item_groups.items():
        for category, dates in category_dates.items():
            if len(dates) > 1:
                frequency = calculate_frequency(dates)
                if frequency:
                    purchase_count = len(dates)
                    last_purchased = dates[-1]
                    next_predicted_date = predict_next_date(last_purchased, frequency)

                    ItemFrequency.objects.update_or_create(
                        user=user,
                        item_description=description,
                        defaults={
                            'category': category,
                            'frequency': frequency,
                            'purchase_count': purchase_count,
                            'last_purchased': last_purchased,
                            'next_predicted_date': next_predicted_date,
                            'confidence_score': 0.8 # Placeholder
                        }
                    )


def calculate_frequency(dates):
    if len(dates) < 2:
        return None

    time_diffs = [(dates[i] - dates[i-1]).days for i in range(1, len(dates))]
    avg_diff = sum(time_diffs) / len(time_diffs)

    if 0 <= avg_diff <= 3:
        return 'daily'
    elif 6 <= avg_diff <= 8:
        return 'weekly'
    elif 28 <= avg_diff <= 32:
        return 'monthly'
    else:
        return 'irregular'

def predict_next_date(last_date, frequency):
    if frequency == 'daily':
        return last_date + timedelta(days=1)
    elif frequency == 'weekly':
        return last_date + timedelta(weeks=1)
    elif frequency == 'monthly':
        return last_date + timedelta(days=30) # Approximation
    else:
        return None
