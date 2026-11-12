FROM mcr.microsoft.com/playwright/python:v1.64.1-noble

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir \
    "playwright==1.64.1" \
    -r requirements.txt

COPY . .

RUN mkdir -p /data

ENV GEOGRID_DB=/data/geogrid.db
ENV GEOGRID_FETCHER=dataforseo
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
