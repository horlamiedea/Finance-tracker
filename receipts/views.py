from rest_framework import generics, permissions
from rest_framework.parsers import MultiPartParser
from .models import Receipt
from .serializers import ReceiptSerializer
from transactions.models import Transaction
from transactions.services.ocr_service import OCRService
from transactions.services.ai_service import AIService
import os
import json
from datetime import datetime

class ReceiptProcessView(generics.CreateAPIView):
    serializer_class = ReceiptSerializer
    parser_classes = [MultiPartParser]
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        user = self.request.user
        receipt = serializer.save(user=user)

        # OCR processing
        img_path = receipt.uploaded_image.path
        extracted_text = OCRService.extract_text(img_path)

        # AI processing
        openai_api_key = os.getenv('OPENAI_API_KEY')
        ai_service = AIService(openai_api_key)
        ai_response = ai_service.categorize_expenses(extracted_text)

        try:
            parsed_data = json.loads(ai_response)
            receipt.extracted_text = extracted_text
            receipt.items = parsed_data.get("items", [])
            receipt.save()

            # Attempt to match with existing transaction by total and date
            total_amount = parsed_data.get('total')
            transaction_date = datetime.strptime(parsed_data.get('date'), '%Y-%m-%d')

            transaction = Transaction.objects.filter(
                user=user,
                amount=total_amount,
                date__date=transaction_date.date(),
                transaction_type='debit'
            ).first()

            if transaction:
                receipt.transaction = transaction
                receipt.save()

        except json.JSONDecodeError:
            print("AI response wasn't valid JSON:", ai_response)