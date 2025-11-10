
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from email.mime.image import MIMEImage
import requests
from django.template.loader import render_to_string
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
    """
    Sends a multi-part (text + HTML) welcome email using the responsive HTML template.
    Downloads the logo PNG at send time and embeds it inline via Content-ID so
    the template's <img src="cid:logo.png"> renders across clients.
    """
    subject = WELCOME_SUBJECT
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or getattr(settings, "SERVER_EMAIL", None)
    recipient_list = [registration.email]

    context = {"first_name": registration.first_name}
    html_content = render_to_string("conference/welcome_email.html", context)
    text_content = build_welcome_body(registration.first_name)

    message = EmailMultiAlternatives(subject, text_content, from_email, recipient_list)
    message.attach_alternative(html_content, "text/html")

    # Attach inline logo from remote PNG as CID so emails don't depend on remote loading.
    try:
        logo_url = "https://castellum.blob.core.windows.net/media/Group%2034190.png"
        resp = requests.get(logo_url, timeout=10)
        if resp.status_code == 200 and resp.content:
            img = MIMEImage(resp.content, _subtype="png")
            img.add_header("Content-ID", "<logo.png>")
            img.add_header("Content-Disposition", "inline", filename="logo.png")
            message.attach(img)
    except Exception:
        # Swallow image errors to avoid breaking email delivery
        pass

    # Fail silently to keep API UX smooth; rely on server logs for diagnostics.
    message.send(fail_silently=True)


class FreedomConferenceRegistrationCreateView(generics.CreateAPIView):
    queryset = FreedomConferenceRegistration.objects.all()
    serializer_class = FreedomConferenceRegistrationSerializer
    # Public endpoint for the landing page form
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        instance = serializer.save()
        send_welcome_email(instance)
        return instance
