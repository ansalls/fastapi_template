FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir uv \
    && uv pip install --system --no-cache -r requirements.txt

RUN groupadd --system app && useradd --system --gid app --create-home app
COPY --chown=app:app . .

EXPOSE 8000
USER app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
