from django.urls import path
from .views import FreedomConferenceRegistrationCreateView

urlpatterns = [
    path("register/", FreedomConferenceRegistrationCreateView.as_view(), name="conference-register"),
]
