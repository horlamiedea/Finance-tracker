import io
import matplotlib
# Use a non-interactive backend to prevent GUI errors in the server thread.
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta, datetime

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.units import inch

from .models import Transaction

class PDFReportGenerator:
    """
    A dedicated class to handle the logic of generating a financial PDF report.
    This encapsulates all data fetching and PDF rendering, keeping the view clean.
    """
    def __init__(self, user, start_date=None, end_date=None):
        self.user = user
        self.styles = getSampleStyleSheet()
        self.story = []
        
        # THE FIX: Standardize date handling to ensure the full end_date is included.
        # We now work with timezone-aware datetime objects for precision.
        if end_date:
            # Convert date to datetime at the end of the day
            self.end_date = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
        else:
            self.end_date = timezone.now()

        if start_date:
            # Convert date to datetime at the beginning of the day
            self.start_date = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
        else:
            # Default to the last 30 days from the end_date
            self.start_date = self.end_date - timedelta(days=30)


    def generate(self) -> io.BytesIO:
        """
        The main method to generate the full PDF report and return it as a byte buffer.
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=inch, leftMargin=inch, topMargin=inch, bottomMargin=inch)
        
        self._add_header()
        
        transactions = Transaction.objects.filter(user=self.user, date__range=[self.start_date, self.end_date])
        debits = transactions.filter(transaction_type='debit')
        credits = transactions.filter(transaction_type='credit')
        
        total_spent = debits.aggregate(Sum('amount'))['amount__sum'] or 0
        total_earned = credits.aggregate(Sum('amount'))['amount__sum'] or 0
        
        self._add_summary_dashboard(total_earned, total_spent)
        
        spending_by_category = debits.values('category__name').annotate(total=Sum('amount')).order_by('-total')
        if spending_by_category:
            self._add_spending_chart(spending_by_category, total_spent)
        
        self._add_budget_forecast(spending_by_category)
        
        self._add_transaction_table(debits)
        
        doc.build(self.story)
        buffer.seek(0)
        return buffer

    def _add_header(self):
        self.story.append(Paragraph("Your Financial Report", self.styles['h1']))
        self.story.append(Paragraph(f"For {self.start_date.strftime('%B %d, %Y')} to {self.end_date.strftime('%B %d, %Y')}", self.styles['h3']))
        self.story.append(Spacer(1, 0.25 * inch))

    def _add_summary_dashboard(self, total_earned, total_spent):
        net_savings = total_earned - total_spent
        summary_data = [
            ['Total Income:', f"₦{total_earned:,.2f}", 'Total Expenses:', f"₦{total_spent:,.2f}"],
            ['Net Savings:', f"₦{net_savings:,.2f}", '', '']
        ]
        table = Table(summary_data, colWidths=[1.5*inch, 1.5*inch, 1.5*inch, 1.5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (0,1), colors.HexColor("#D5E8D4")),
            ('BACKGROUND', (2,0), (2,0), colors.HexColor("#F8CECC")),
            ('TEXTCOLOR', (0,0), (-1,-1), colors.HexColor("#333333")),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 12),
            ('GRID', (0,0), (-1,-1), 1, colors.white)
        ]))
        self.story.append(table)
        self.story.append(Spacer(1, 0.25 * inch))

    def _add_spending_chart(self, data, total_spent):
        """
        THE FIX: This method now creates a much cleaner "donut" chart by grouping
        small categories into an "Others" slice.
        """
        self.story.append(Paragraph("Spending by Category", self.styles['h2']))
        
        labels = []
        sizes = []
        others_total = 0
        
        # Group categories that are less than 3% of total spending
        for item in data:
            percentage = (item['total'] / total_spent) * 100 if total_spent > 0 else 0
            if percentage < 3:
                others_total += item['total']
            else:
                labels.append(item['category__name'] or "Uncategorized")
                sizes.append(item['total'])
        
        if others_total > 0:
            labels.append("Others")
            sizes.append(others_total)
            
        # Define a professional color palette
        colors_palette = plt.cm.Pastel2(np.linspace(0, 1, len(labels)))
        
        fig, ax = plt.subplots(figsize=(6, 4))
        
        # Create the donut chart
        wedges, texts, autotexts = ax.pie(
            sizes, 
            labels=labels, 
            autopct='%1.1f%%', 
            startangle=90, 
            colors=colors_palette, 
            wedgeprops=dict(width=0.4, edgecolor='w'),
            pctdistance=0.80 # Move percentage text inside the donut
        )
        
        # Improve label appearance
        plt.setp(autotexts, size=8, weight="bold", color="white")
        plt.setp(texts, size=10)
        
        ax.axis('equal')
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', transparent=True, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        
        self.story.append(Image(buf, width=5*inch, height=3.5*inch))
        self.story.append(Spacer(1, 0.25 * inch))

    def _add_budget_forecast(self, spending_this_period):
        """
        This method now provides a much more intelligent forecast
        by analyzing spending trends against a 90-day average.
        """
        self.story.append(Paragraph("Trend-Based Budget Forecast", self.styles['h2']))
        
        # 1. Get 90-day spending data for trend analysis
        historical_days = 90
        historical_start_date = self.end_date - timedelta(days=historical_days)
        spending_90_days = Transaction.objects.filter(
            user=self.user, transaction_type='debit', date__range=[historical_start_date, self.end_date]
        ).values('category__name').annotate(total=Sum('amount'))
        
        # 2. THE FIX: Create a more precise lookup for 30-day average spend
        avg_monthly_spend_90_days = {
            item['category__name']: ((item['total'] or 0) / historical_days) * 30
            for item in spending_90_days
        }

        # 3. Build the forecast table data
        forecast_data = [['Category', 'This Period', '30-Day Forecast', 'Trend']]
        total_forecast = 0

        for item in spending_this_period:
            category_name = item['category__name'] or "Uncategorized"
            current_spend = item['total'] or 0
            
            num_days_in_period = (self.end_date - self.start_date).days
            daily_spend = current_spend / num_days_in_period if num_days_in_period > 0 else 0
            projected_spend = daily_spend * 30
            total_forecast += projected_spend
            
            avg_spend = avg_monthly_spend_90_days.get(category_name, 0)
            trend_text = "Stable"
            trend_color = colors.black
            if avg_spend > 0:
                percentage_diff = ((projected_spend - avg_spend) / avg_spend) * 100
                if percentage_diff > 10:
                    trend_text = f"▲ {percentage_diff:.0f}% Increase"
                    trend_color = colors.HexColor('#9C0006') # Red
                elif percentage_diff < -10:
                    trend_text = f"▼ {abs(percentage_diff):.0f}% Decrease"
                    trend_color = colors.HexColor('#006100') # Green
            
            forecast_data.append([
                category_name,
                f"₦{current_spend:,.2f}",
                f"₦{projected_spend:,.2f}",
                Paragraph(f'<font color="{trend_color}">{trend_text}</font>', self.styles['BodyText'])
            ])

        # 4. Create and style the forecast table
        table = Table(forecast_data, colWidths=[1.75*inch, 1.5*inch, 1.75*inch, 1.5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#F2F2F2")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.black),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,0), 12),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        self.story.append(table)
        self.story.append(Spacer(1, 0.1 * inch))
        
        # 5. THE FIX: Add a summary paragraph with a clear explanation
        summary_text = f"""
        Your total forecasted budget for the next 30 days is <b>₦{total_forecast:,.2f}</b>.
        The 'Trend' column compares the '30-Day Forecast' to your average monthly spend over the last 90 days.
        """
        self.story.append(Paragraph(summary_text, self.styles['BodyText']))
        self.story.append(Spacer(1, 0.25 * inch))


    def _add_transaction_table(self, debits):
        self.story.append(Paragraph("Recent Debits in Period", self.styles['h2']))
        table_data = [['Date', 'Narration', 'Category', 'Amount']]
        for tx in debits.order_by('-date'):
            table_data.append([
                tx.date.strftime('%Y-%m-%d'),
                Paragraph(tx.narration, self.styles['BodyText']),
                tx.category.name if tx.category else 'Uncategorized',
                f"₦{tx.amount:,.2f}"
            ])
        
        table = Table(table_data, colWidths=[0.8*inch, 3*inch, 1.5*inch, 1*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#DAE8FC")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor("#333333")),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,0), 12),
            ('BACKGROUND', (0,1), (-1,-1), colors.HexColor("#F5F5F5")),
            ('GRID', (0,0), (-1,-1), 1, colors.white),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        self.story.append(table)