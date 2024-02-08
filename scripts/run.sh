#!/bin/sh

# Entrypoint for docker

# start crontab daemon in background
crond -b

# On first run, database needs to be initialized
# this process takes a couple of moments and the database may not
# be up and running, so need to wait until data base is ready
source /powerviz/.env
while ! nc -z ${POSTGRES_HOST} 5432; do sleep 1; done

# start powerviz app
python3.11 app/app.py
