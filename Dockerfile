FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl tzdata && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# The AIY model and labelmap are committed in models/ and arrive with COPY
# above. They used to be downloaded from tfhub.dev here on every build, but
# `curl -sL` doesn't fail on HTTP errors: on 2026-09-24 tfhub.dev started
# returning HTTP 500, the error page got saved as the model, AIY silently
# failed to load, and every photo for a day was auto-rejected. This check
# fails the build loudly instead if the model is ever missing or not a
# real TFLite file ("TFL3" magic at byte offset 4).
RUN python -c "d=open('/app/models/aiy_birds_v1.tflite','rb').read(8); assert d[4:8]==b'TFL3', 'AIY model missing or corrupt'"
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
