FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .[dev]

COPY . .

EXPOSE 3888

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3888", "--workers", "1"]
