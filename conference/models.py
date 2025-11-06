from django.db import models


class FreedomConferenceRegistration(models.Model):
    name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=50)
    email = models.EmailField()
    is_minister = models.BooleanField()
    ministry_name = models.CharField(max_length=255, blank=True)
    ministry_address = models.CharField(max_length=255, blank=True)
    is_first_time = models.BooleanField()
    expectations = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Freedom Conference Registration"
        verbose_name_plural = "Freedom Conference Registrations"

    def __str__(self) -> str:
        return f"{self.name} - {self.email}"

    @property
    def first_name(self) -> str:
        if not self.name:
            return ""
        return self.name.strip().split()[0]
