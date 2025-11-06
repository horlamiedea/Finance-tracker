from django.core.mail import send_mail
from django.conf import settings
from rest_framework import generics, permissions
from .models import FreedomConferenceRegistration
from .serializers import FreedomConferenceRegistrationSerializer


WELCOME_SUBJECT = "You’re In! Welcome to Freedom Conference 2025"


def build_welcome_body(first_name: str) -> str:
    return (
        f"Hey {first_name},\n"
        "You did it! You’re officially registered for Freedom Conference 2025, happening December 10–14 at Freedom Dome, Maryland, Lagos.\n\n"
        "Get ready for four powerful days of worship, prayer, teaching, and encounters that birth true freedom.\n\n"
        "As you count down, stay expectant:\n"
        "Pray and prepare your heart for what God is set to do.\n"
        "Follow @clcglobal on Instagram, Facebook, TikTok, and X for updates.\n"
        "Invite someone — because freedom is best experienced together.\n\n"
        "Freedom is calling — and you’ve answered.\n"
        "See you at Freedom Conference 2025.\n\n"
        "With love,\n"
        "Citizens of Light Church\n\n"
        "“It is for freedom that Christ has set us free, we stand firm then, and do not let ourselves be burdened again by any yoke of slavery. Welcome to Freedom!!!!” - Galatians 5:1\n"
    )


def send_welcome_email(registration: FreedomConferenceRegistration) -> None:
    subject = WELCOME_SUBJECT
    body = build_welcome_body(registration.first_name)
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or getattr(settings, "SERVER_EMAIL", None)
    recipient_list = [registration.email]
    # Fail silently to avoid surfacing email errors to API clients; logs will capture issues.
    send_mail(subject, body, from_email, recipient_list, fail_silently=True)


class FreedomConferenceRegistrationCreateView(generics.CreateAPIView):
    queryset = FreedomConferenceRegistration.objects.all()
    serializer_class = FreedomConferenceRegistrationSerializer
    # Public endpoint for the landing page form
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        instance = serializer.save()
        send_welcome_email(instance)
        return instance
