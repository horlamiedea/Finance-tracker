from rest_framework import generics, permissions
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework import status
from .models import Receipt
from .serializers import ReceiptSerializer
from transactions.models import Transaction
from transactions.services.ocr_service import OCRService
from transactions.services.ai_service import AIService
import os, re
import json
from datetime import datetime, timedelta
from .tasks import process_receipt_upload

# class ReceiptProcessView(generics.CreateAPIView):
#     serializer_class   = ReceiptSerializer
#     parser_classes     = [MultiPartParser]
#     permission_classes = [permissions.IsAuthenticated]

#     def create(self, request, *args, **kwargs):
#         # 1) Save the empty receipt record
#         serializer = self.get_serializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
#         receipt = serializer.save(user=request.user)

#         # 2) Send image to GPT-4 Vision & get parsed_data
#         ai = AIService(api_key=os.getenv("OPENAI_API_KEY"))
#         try:
#             parsed = ai.categorize_expenses_from_image(receipt.uploaded_image.path)
#         except ValueError as e:
#             return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

#         # 3) Persist line-items (always trust the API data)
#         receipt.extracted_text = None
#         receipt.items          = parsed["items"]
#         receipt.save()

#         # 4) Build matching queryset
#         user        = request.user
#         total       = parsed.get("total")
#         tx_type     = "debit"  # or derive from parsed if you also extract it
#         qs          = Transaction.objects.filter(
#             user=user,
#             amount=total,
#             transaction_type=tx_type
#         )

#         # 5) Parse the receipt’s date (fallback to upload_date)
#         raw_date = parsed.get("date", "")
#         try:
#             receipt_dt = datetime.fromisoformat(raw_date)
#         except Exception:
#             receipt_dt = receipt.upload_date

#         matched = None

#         # 6a) Exact calendar-day match
#         same_day = qs.filter(date__date=receipt_dt.date())
#         if same_day.exists():
#             matched = same_day.first()
#         else:
#             # 6b) Expand to ±1 day
#             start = receipt_dt - timedelta(days=1)
#             end   = receipt_dt + timedelta(days=1)
#             window = qs.filter(date__range=(start, end))
#             if window.exists():
#                 # pick the one whose timestamp is closest to receipt_dt
#                 matched = min(
#                     window,
#                     key=lambda tx: abs(tx.date - receipt_dt)
#                 )
#             else:
#                 # 6c) Fallback: pick the most recent with that amount
#                 matched = qs.order_by("-date").first()

#         # 7) Link it (if any) and save
#         if matched:
#             receipt.transaction = matched
#             receipt.save()

#         # 8) Return full payload
#         return Response({
#             "receipt": ReceiptSerializer(receipt).data,
#             "parsed_data": parsed,
#             "matched_transaction_id": matched.id if matched else None
#         }, status=status.HTTP_201_CREATED)



class ReceiptProcessView(generics.CreateAPIView):
    """
    POST /api/receipts/upload/
    — Accepts an image file, creates a Receipt record, and enqueues
      background processing to extract line-items & link to a Transaction.
    """
    serializer_class   = ReceiptSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes     = [MultiPartParser]

    def create(self, request, *args, **kwargs):
        uploaded_image = request.FILES.get('uploaded_image')
        if not uploaded_image:
            return Response({"error": "No image provided."}, status=status.HTTP_400_BAD_REQUEST)

        # Create a new Receipt instance
        receipt = Receipt(user=request.user)
        
        # Upload the image to Azure and set the URL on the receipt instance
        receipt.upload_to_azure(uploaded_image)
        
        # Now save the receipt instance with the Azure URL to the DB
        receipt.save()
        
        # Trigger the background task
        process_receipt_upload.delay(receipt.id)
        
        serializer = self.get_serializer(receipt)
        data = {
            "receipt": serializer.data,
            "message": "Receipt uploaded successfully. Line-items will be extracted in the background."
        }
        return Response(data, status=status.HTTP_201_CREATED)
