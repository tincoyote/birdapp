FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/models && \
    curl -sL -o /app/models/aiy_birds_v1.tflite "https://tfhub.dev/google/lite-model/aiy/vision/classifier/birds_V1/3?lite-format=tflite" && \
    curl -sL -o /app/models/aiy_birds_labelmap.csv "https://www.gstatic.com/aihub/tfhub/labelmaps/aiy_birds_V1_labelmap.csv"
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
