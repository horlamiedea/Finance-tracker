from __future__ import absolute_import
import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
app = Celery('finance_tracker')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'sync-all-users-transactions-daily': {
        'task': 'transactions.tasks.sync_all_users_transactions_daily',
        'schedule': crontab(hour=0, minute=0),  # Midnight
    },
}
