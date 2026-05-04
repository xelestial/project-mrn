FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY apps/server/requirements.txt /app/apps/server/requirements.txt
RUN pip install --no-cache-dir -r /app/apps/server/requirements.txt

COPY apps/server /app/apps/server
COPY engine /app/engine
COPY packages/ui-domain /app/packages/ui-domain
COPY packages/runtime-contracts /app/packages/runtime-contracts

EXPOSE 9090

CMD ["python", "-m", "uvicorn", "apps.server.src.app:app", "--host", "0.0.0.0", "--port", "9090"]
