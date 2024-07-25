#!/bin/bash

export PYTHONPATH="/apps/vocodia-dev/lib/python3.12/site-packages"

cd ${PYTHONPATH} || exit;
/apps/vocodia-dev/bin/gunicorn --preload --workers 4 --bind 0.0.0.0:8080 --error-logfile /var/log/gunicorn/error.log --access-logfile /var/log/gunicorn/access.log app.main:app
