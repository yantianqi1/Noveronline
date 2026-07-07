FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY mirofish_agents ./mirofish_agents

RUN pip install --no-cache-dir .

CMD ["python", "-m", "mirofish_agents.temporal.worker"]
