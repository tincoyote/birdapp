FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl tzdata && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-detector.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# --- MegaDetector (2026-10-20, see docs/PLAN-detector.md) ---
# Order matters. CPU-only PyTorch first, from PyTorch's own index: the
# default PyPI build bundles CUDA (~3 GB more) for a GPU this NAS doesn't
# have. Then the pinned inference deps, then yolov5 with --no-deps so pip
# can't replace that torch or pull numpy 2 (which breaks tflite-runtime).
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
        torch==2.5.1 torchvision==0.20.1
RUN pip install --no-cache-dir -r requirements-detector.txt \
 && pip install --no-cache-dir --no-deps yolov5==7.0.11

# The weights (281 MB) are too big for git, so they're downloaded here -
# but checked, because a bad download is exactly what broke AIY on
# 2026-09-24 (tfhub.dev returned an error page, curl -sL saved it as the
# model, every photo was auto-rejected for a day). --fail makes curl error
# on HTTP errors, and sha256sum -c fails the build if the file isn't the
# exact MegaDetector v5a.0.1 release (same file SpeciesNet used).
RUN mkdir -p /app/models \
 && curl -sSfL --retry 3 -o /app/models/md_v5a.0.1.pt \
        https://github.com/agentmorris/MegaDetector/releases/download/v5.0/md_v5a.0.1.pt \
 && echo "fe3e90e4b1955821ab7c1f88b446dc0c8cb25e109fdd1872916a55305294a5ef  /app/models/md_v5a.0.1.pt" | sha256sum -c -

COPY . .
# The AIY model and labelmap are committed in models/ and arrive with COPY
# above. They used to be downloaded from tfhub.dev here on every build, but
# `curl -sL` doesn't fail on HTTP errors: on 2026-09-24 tfhub.dev started
# returning HTTP 500, the error page got saved as the model, AIY silently
# failed to load, and every photo for a day was auto-rejected. This check
# fails the build loudly instead if the model is ever missing or not a
# real TFLite file ("TFL3" magic at byte offset 4).
RUN python -c "d=open('/app/models/aiy_birds_v1.tflite','rb').read(8); assert d[4:8]==b'TFL3', 'AIY model missing or corrupt'"
# Fail the build (not the first photo) if the detector stack can't load:
# imports, weights unpickling and one inference on a blank frame.
RUN python -c "import detector; from PIL import Image; md = detector.MegaDetector('/app/models/md_v5a.0.1.pt', 640, 2); print('MegaDetector OK:', md.detect(Image.new('RGB', (640, 360)), 0.1))"
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
