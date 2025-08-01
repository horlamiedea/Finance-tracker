# Generated by Django 5.2.1 on 2025-07-23 10:32

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0008_delete_rawemail2"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="transaction",
            options={"ordering": ["-date"]},
        ),
        migrations.RemoveField(
            model_name="transaction",
            name="reference_id",
        ),
        migrations.RemoveField(
            model_name="transaction",
            name="sender_receiver",
        ),
        migrations.AlterField(
            model_name="rawemail",
            name="email_id",
            field=models.CharField(max_length=255),
        ),
        migrations.AlterField(
            model_name="rawemail",
            name="parsing_method",
            field=models.CharField(
                choices=[
                    ("none", "None"),
                    ("ai_success", "AI Success"),
                    ("ai_failed", "AI Failed to Parse"),
                    (
                        "creation_failed_data_error",
                        "Transaction Creation Failed (Data Error)",
                    ),
                    (
                        "creation_failed_unknown",
                        "Transaction Creation Failed (Unknown Error)",
                    ),
                ],
                default="none",
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="transaction",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="transactions",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterUniqueTogether(
            name="rawemail",
            unique_together={("user", "email_id")},
        ),
        migrations.CreateModel(
            name="Budget",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(default="Monthly Budget", max_length=100)),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                (
                    "total_amount",
                    models.DecimalField(decimal_places=2, default=0, max_digits=15),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="budgets",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-start_date"],
                "unique_together": {("user", "name", "start_date")},
            },
        ),
        migrations.CreateModel(
            name="BudgetItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "budgeted_amount",
                    models.DecimalField(decimal_places=2, max_digits=15),
                ),
                (
                    "budget",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="transactions.budget",
                    ),
                ),
                (
                    "category",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="transactions.transactioncategory",
                    ),
                ),
            ],
        ),
    ]
