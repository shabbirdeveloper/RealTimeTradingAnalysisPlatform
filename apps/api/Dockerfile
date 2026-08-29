# Production image for the market-data collector service (spec:
# "Trading/signal engine: AWS/VPS/Docker"). Not deployed anywhere yet --
# this is the scaffold for when it is.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
