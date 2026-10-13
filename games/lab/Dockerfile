FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        ffmpeg \
        libstdc++6 \
        openssh-client \
        zlib1g \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY requirements.txt /tmp/requirements.txt
# Requirements first. The CUDA wheel is installed after so PyPI cannot replace it.
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cu130 torch

ENV PYTHONUNBUFFERED=1 \
    LAB_HOME=/lab \
    LAB_RUNS=/runs \
    LAB_PORT=8790 \
    SDL_AUDIODRIVER=dummy \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1

EXPOSE 8790
CMD ["python", "-m", "games.lab.server"]
