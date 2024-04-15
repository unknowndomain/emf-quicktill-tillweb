#!/bin/sh

# Current directory is /app when this script is executed

./manage.py migrate
exec gunicorn -k gthread -w 6 -b '0.0.0.0:8000' --preload --access-logfile - tillweb_infra.wsgi:application
