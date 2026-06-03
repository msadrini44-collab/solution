# AntiDeepfake AI — backend container
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# System libraries needed by OpenCV, dlib, librosa (audio), and matplotlib.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake \
    libgl1 libglib2.0-0 \
    libsndfile1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for better layer caching.
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --upgrade pip && \
    pip install -r /app/backend/requirements.txt

# Copy the application code.
COPY backend /app/backend
COPY scripts /app/scripts

# Pretrained weights are downloaded at build or first run. Uncomment to bake
# them into the image (increases image size considerably):
# RUN python scripts/download_models.py

EXPOSE 8000

# Run the API. The pipeline executes via FastAPI BackgroundTasks by default;
# set up the Celery worker separately (see docker-compose.yml) to scale out.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
