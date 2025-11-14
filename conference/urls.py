from django.urls import path
from .views import FreedomConferenceRegistrationCreateView, export_freedom_conference_registrations_csv

urlpatterns = [
    path("register/", FreedomConferenceRegistrationCreateView.as_view(), name="conference-register"),
    path("registrations/export/", export_freedom_conference_registrations_csv, name="conference-registrations-export"),
]
