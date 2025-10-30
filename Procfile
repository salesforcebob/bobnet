web: gunicorn app.web:app -k uvicorn.workers.UvicornWorker --log-level info
worker: rq worker --url $REDIS_URL email_simulator
