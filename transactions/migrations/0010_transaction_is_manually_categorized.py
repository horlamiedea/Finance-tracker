# Generated by Django 5.2.1 on 2025-07-24 11:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0009_alter_transaction_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="is_manually_categorized",
            field=models.BooleanField(default=False),
        ),
    ]
