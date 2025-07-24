from django.apps import AppConfig


class TransactionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "transactions"

    def ready(self):
        # Import signals so they are connected when the app starts.
        import transactions.signals


