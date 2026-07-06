FROM python:3.12-slim

WORKDIR /app

# postgresql-client provides psql + pg_isready, used by docker-entrypoint.sh to
# wait for the DB and apply migrations idempotently on boot.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy the full package BEFORE installing: the editable install needs the `app`
# package present so setuptools' package discovery (include = ["app*"]) resolves.
COPY . .
RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app
RUN chmod +x docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
