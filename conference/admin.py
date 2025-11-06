from django.contrib import admin
from .models import FreedomConferenceRegistration


@admin.register(FreedomConferenceRegistration)
class FreedomConferenceRegistrationAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "phone_number", "is_minister", "is_first_time", "created_at")
    search_fields = ("name", "email", "phone_number", "ministry_name")
    list_filter = ("is_minister", "is_first_time", "created_at")
    readonly_fields = ("created_at",)
