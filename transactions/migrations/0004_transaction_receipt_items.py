# Generated by Django 5.1.4 on 2025-05-25 23:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('transactions', '0003_rawemail'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='receipt_items',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
