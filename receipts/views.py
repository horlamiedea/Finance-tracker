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
from datetime import datetime

class ReceiptProcessView(generics.CreateAPIView):
    serializer_class   = ReceiptSerializer
    parser_classes     = [MultiPartParser]
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        # 1) Save the empty receipt record
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        receipt = serializer.save(user=request.user)

        # 2) Send image directly to GPT-4 Vision
        ai = AIService(api_key=os.getenv("OPENAI_API_KEY"))
        try:
            parsed = ai.categorize_expenses_from_image(receipt.uploaded_image.path)
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3) Persist the API results
        receipt.extracted_text = None     # no OCR string, since we used vision directly
        receipt.items          = parsed["items"]
        receipt.save()

        # 4) Try to match an existing transaction
        matched = None
        try:
            tx_date = datetime.strptime(parsed["date"], "%Y-%m-%d").date()
            matched = Transaction.objects.filter(
                user=request.user,
                amount=parsed["total"],
                date__date=tx_date,
                transaction_type="debit"
            ).first()
            if matched:
                receipt.transaction = matched
                receipt.save()
        except Exception:
            matched = None

        # 5) Return everything in one JSON payload
        return Response({
            "receipt": ReceiptSerializer(receipt).data,
            "parsed_data": parsed,
            "matched_transaction_id": matched.id if matched else None
        }, status=status.HTTP_201_CREATED)