from rest_framework import serializers
from .models import FreedomConferenceRegistration


class FreedomConferenceRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = FreedomConferenceRegistration
        fields = [
            "id",
            "name",
            "phone_number",
            "email",
            "is_minister",
            "ministry_name",
            "ministry_address",
            "is_first_time",
            "expectations",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        # If not a minister, blank-out optional ministry details
        if not attrs.get("is_minister"):
            attrs["ministry_name"] = ""
            attrs["ministry_address"] = ""
        return attrs
