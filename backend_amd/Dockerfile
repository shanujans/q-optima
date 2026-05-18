# backend_amd/Dockerfile
# AMD GPU perception node.
# Base: official ROCm PyTorch — gives HIP-enabled torch without reinstalling.
# NEVER run pip install torch inside here — it pulls the CUDA build from PyPI.

FROM rocm/pytorch:rocm6.1_ubuntu22.04_py3.10_pytorch_2.1.2

LABEL description="Q-Optima AMD perception node — Whisper ROCm"

# ffmpeg: required by openai-whisper for audio decoding
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libsndfile1 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install only the non-torch deps
COPY requirements_amd.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements_amd.txt

COPY . .

# Pre-download Whisper model at build time so container starts instantly
ARG WHISPER_MODEL=base
ENV WHISPER_MODEL=${WHISPER_MODEL}
RUN python -c "import whisper; whisper.load_model('${WHISPER_MODEL}')"

# ROCm device environment
ENV HSA_OVERRIDE_GFX_VERSION=10.3.0
ENV PYTORCH_HIP_ALLOC_CONF=max_split_size_mb:512

RUN adduser --disabled-password --gecos "" appuser \
 && chown -R appuser:appuser /app
USER appuser

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=15s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8001/api/health || exit 1

CMD ["uvicorn", "whisper_service:app", \
     "--host", "0.0.0.0", "--port", "8001", \
     "--workers", "1", "--log-level", "info"]
