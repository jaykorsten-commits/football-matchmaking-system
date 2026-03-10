release: python -c "import os; url=os.environ.get('DATABASE_URL') or ''; exit(0 if url and 'rds.' in url else 1)"
web: python heroku_env_check.py; exec gunicorn -w 1 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT --preload Admin.main:app
