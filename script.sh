celery -A config worker -l info
python3 manage.py runserver



gunicorn config.wsgi:application --bind 0.0.0.0:443 --certfile=/etc/letsencrypt/archive/financetracker.eastus.cloudapp.azure.com/cert1.pem --keyfile=/etc/letsencrypt/archive/financetracker.eastus.cloudapp.azure.com/privkey1.pem