release: python -c "import os; url=os.environ.get('DATABASE_URL') or ''; exit(0 if url and 'rds.' in url else 1)"
web: sh -c 'uvicorn Admin.main:app --host 0.0.0.0 --port ${PORT}'
