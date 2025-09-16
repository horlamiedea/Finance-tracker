import os
from celery import shared_task
from django.utils import timezone

from receipts.models        import Receipt

from transactions.models    import Transaction
from transactions.services.ai_service   import AIService
from django.db import models
import json
from datetime import timedelta
from django.db import IntegrityError


@shared_task
def process_receipt_upload(receipt_id: int):
    """
    Re-process the receipt image → parsed JSON → match → link flow,
    but handle already-attached receipts gracefully.
    """
    try:
        receipt = Receipt.objects.get(id=receipt_id)
    except Receipt.DoesNotExist:
        return f"Receipt {receipt_id} no longer exists."
    if receipt.transaction_id:
        return f"Receipt {receipt_id} already attached to Tx {receipt.transaction_id}; skipping."
    ai = AIService()
    try:
        parsed = ai.extract_data_from_receipt(receipt.uploaded_image.path)
    except Exception as e:
        return f"AI parse failed for receipt {receipt_id}: {e}"
    receipt.extracted_text = json.dumps(parsed)
    receipt.items          = parsed.get("items", [])
    receipt.save()

    # 3) find matching transaction
    tx_qs = Transaction.objects.filter(
        user=receipt.user,
        amount=parsed["total"],
        transaction_type="debit"
    )
    try:
        receipt_dt = timezone.datetime.fromisoformat(parsed["date"])
    except Exception:
        receipt_dt = receipt.upload_date

    # exact date
    tx = tx_qs.filter(date__date=receipt_dt.date()).first()
    if not tx:
        # ±1 day window
        start, end = receipt_dt - timedelta(days=1), receipt_dt + timedelta(days=1)
        window = tx_qs.filter(date__range=(start, end))
        if window.exists():
            tx = min(window, key=lambda t: abs(t.date - receipt_dt))
        else:
            tx = tx_qs.order_by("-date").first()

    if not tx:
        return f"No matching transaction for receipt {receipt_id}"

    tx.receipt_items = parsed["items"]
    tx.save()
    receipt.transaction = tx
    try:
        receipt.save()
    except IntegrityError:
        return f"Receipt {receipt_id} was already linked in a race; discarding update."

    return f"Receipt {receipt_id} successfully linked to Tx {tx.id}"

@shared_task
def reconcile_unprocessed_receipts():
    """
    Find any receipts which either:
      - have no transaction linked, or
      - whose transaction.receipt_items is empty,
    and re-run processing.
    """
    to_check = Receipt.objects.filter(
        # no txn yet OR txn has no items
        models.Q(transaction__isnull=True) |
        models.Q(transaction__receipt_items__isnull=True)
    )
    for r in to_check:
        process_receipt_upload.delay(r.id)
    return f"Enqueued {to_check.count()} receipts for reprocessing."
