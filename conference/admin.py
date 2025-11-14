from django.contrib import admin
from django.http import HttpResponse
from django.utils import timezone
import csv
from .models import FreedomConferenceRegistration


@admin.register(FreedomConferenceRegistration)
class FreedomConferenceRegistrationAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "phone_number", "is_minister", "is_first_time", "created_at")
    search_fields = ("name", "email", "phone_number", "ministry_name")
    list_filter = ("is_minister", "is_first_time", "created_at")
    readonly_fields = ("created_at",)
    actions = ("export_as_csv",)

    @admin.action(description="Export selected registrations as CSV")
    def export_as_csv(self, request, queryset):
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="freedom_registrations_{timestamp}.csv"'
        writer = csv.writer(response)
        # Header
        writer.writerow(
            [
                "Name",
                "Email",
                "Phone Number",
                "Is Minister",
                "Ministry Name",
                "Ministry Address",
                "Is First Time",
                "Expectations",
                "Created At",
            ]
        )
        for obj in queryset.order_by("-created_at"):
            writer.writerow(
                [
                    obj.name,
                    obj.email,
                    obj.phone_number,
                    "Yes" if obj.is_minister else "No",
                    obj.ministry_name,
                    obj.ministry_address,
                    "Yes" if obj.is_first_time else "No",
                    (obj.expectations or "").replace("\r\n", " ").replace("\n", " "),
                    obj.created_at.isoformat(),
                ]
            )
        return response
