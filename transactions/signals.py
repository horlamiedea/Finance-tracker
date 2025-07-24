import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Transaction
from .tasks import reconcile_similar_transactions_task

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Transaction)
def trigger_transaction_reconciliation(sender, instance, created, **kwargs):
    """
    Listens for saves on the Transaction model. If a category was manually updated,
    it triggers a background task to find and update similar transactions.
    """
    # We only care about updates where the 'is_manually_categorized' flag has been set to True.
    if not created and instance.is_manually_categorized:
        logger.info(f"Manual category change detected for Tx {instance.id}. Triggering reconciliation task.")
        
        # Trigger the background task to do the heavy lifting.
        reconcile_similar_transactions_task.delay(instance.id)
        
        # Reset the flag to False immediately using a direct update.
        # This prevents the signal from re-triggering on subsequent saves of this instance.
        Transaction.objects.filter(pk=instance.pk).update(is_manually_categorized=False)
