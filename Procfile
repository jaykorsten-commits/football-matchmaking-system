release: python -c "import os; url=os.environ.get('DATABASE_URL') or ''; exit(0 if url and 'rds.' in url else 1)"
web: python -c "import os; print('HAS_DATABASE_URL:', bool(os.environ.get('DATABASE_URL')))" && gunicorn -w 1 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT --preload Admin.main:app
