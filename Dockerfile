FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt ./
RUN python -m pip install -r requirements.txt

COPY . .
RUN AGENDE_DEBUG=0 python manage.py collectstatic --noinput

EXPOSE 8080

CMD ["python", "scripts/iniciar_runsite.py"]
