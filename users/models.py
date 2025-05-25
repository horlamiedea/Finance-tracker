from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    gmail_token = models.TextField(blank=True, null=True)
    gmail_refresh_token = models.TextField(blank=True, null=True)