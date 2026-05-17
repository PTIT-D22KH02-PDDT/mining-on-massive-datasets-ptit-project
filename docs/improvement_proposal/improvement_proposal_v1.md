# Improvement Proposal
**Date:** 2026-05-17
**Version:** v1

---

## Contents

- [v1.2 — Docker Optimization: Split into 4 Images](#v12--docker-optimization-split-into-4-images)

---

## v1.2 — Docker Optimization: Split into 4 Images

**Status:** Proposed (not yet implemented)
**Date:** 2026-05-17

### Mục tiêu
Tách 1 image chung thành 4 images riêng biệt, mỗi image chỉ chứa dependencies cần thiết cho service tương ứng. Giảm tổng image size từ ~1.5-2GB xuống ~1GB.

### Base image
- `python:3.12-alpine` (~50MB thay vì ~150MB của `slim`)
- `openjdk21-jre-alpine` (~60MB thay vì ~250MB của `default-jre`)

### Cấu trúc files đề xuất

```
├── Dockerfile.api              # API service
├── Dockerfile.streaming        # Spark streaming
├── Dockerfile.dashboard        # Streamlit dashboard
├── Dockerfile.setup           # Setup jobs
├── docker-compose.yml          # Production (dùng pre-built images)
├── docker-compose.dev.yml      # Dev (mount source code)
├── .dockerignore
└── Makefile
```

### Dockerfiles

**Dockerfile.api** (không có Java)
```dockerfile
FROM python:3.12-alpine
WORKDIR /opt/app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-dev
COPY src/ src/ config/ config/
ENV PATH="/opt/app/.venv/bin:$PATH"
CMD ["python3", "src/api/main.py"]
```

**Dockerfile.streaming** (có Java)
```dockerfile
FROM python:3.12-alpine
RUN apk add --no-cache openjdk21-jre-base bash && pip install --no-cache-dir uv
WORKDIR /opt/app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-dev
COPY src/ src/ config/ config/
ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk
ENV PATH="/opt/app/.venv/bin:$JAVA_HOME/bin:$PATH"
CMD ["python3", "src/streaming/spark_streaming_job.py"]
```

**Dockerfile.dashboard** (không có Java)
```dockerfile
FROM python:3.12-alpine
RUN pip install --no-cache-dir uv
WORKDIR /opt/app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-dev
COPY src/ src/ config/ config/ streamlit_app.py .
ENV PATH="/opt/app/.venv/bin:$PATH"
CMD ["streamlit", "run", "streamlit_app.py"]
```

**Dockerfile.setup** (có Java)
```dockerfile
FROM python:3.12-alpine
RUN apk add --no-cache openjdk21-jre-base bash && pip install --no-cache-dir uv
WORKDIR /opt/app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-dev
COPY src/ src/ config/ config/
ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk
ENV PATH="/opt/app/.venv/bin:$JAVA_HOME/bin:$PATH"
CMD ["python3", "src/batch/funnel_analysis.py"]
```

### Docker Compose

**Production** (`docker-compose.yml`): Dùng `image:` đã build, không mount source.

**Dev** (`docker-compose.dev.yml`): Override bằng `build:` và thêm `volumes:` để mount source code. `setup-jobs` không có trong dev vì chạy 1 lần rồi exit.

### Makefile

```makefile
REGISTRY ?= $(DOCKER_USERNAME)
TAG ?= latest

build:
	docker build -f Dockerfile.api -t $(REGISTRY)/otto-api:$(TAG) .
	docker build -f Dockerfile.streaming -t $(REGISTRY)/otto-spark-streaming:$(TAG) .
	docker build -f Dockerfile.dashboard -t $(REGISTRY)/otto-dashboard:$(TAG) .
	docker build -f Dockerfile.setup -t $(REGISTRY)/otto-setup:$(TAG) .

push:
	docker push $(REGISTRY)/otto-api:$(TAG)
	docker push $(REGISTRY)/otto-spark-streaming:$(TAG)
	docker push $(REGISTRY)/otto-dashboard:$(TAG)
	docker push $(REGISTRY)/otto-setup:$(TAG)

build-push: build push

build-dev:
	docker build -f Dockerfile.api -t $(REGISTRY)/otto-api:$(TAG)-dev .
	docker build -f Dockerfile.streaming -t $(REGISTRY)/otto-spark-streaming:$(TAG)-dev .
	docker build -f Dockerfile.dashboard -t $(REGISTRY)/otto-dashboard:$(TAG)-dev .

clean:
	docker rmi $(REGISTRY)/otto-api:$(TAG) $(REGISTRY)/otto-spark-streaming:$(TAG) \
		$(REGISTRY)/otto-dashboard:$(TAG) $(REGISTRY)/otto-setup:$(TAG) 2>/dev/null || true

.PHONY: build push build-push build-dev clean
```

### Ước tính size

| Image | Base + deps | Java | Tổng |
|-------|------------|------|------|
| api | ~150MB | 0 | ~150-200MB |
| dashboard | ~200MB | 0 | ~200-250MB |
| spark-streaming | ~200MB | ~80MB | ~280-350MB |
| setup | ~200MB | ~80MB | ~280-350MB |
| **Tổng** | | | **~1GB** |

### Cách dùng

```bash
# Production
make build && make push
docker compose up -d

# Dev (mount source, không cần rebuild khi edit code)
make build-dev
docker compose -f docker-compose.yml -f docker-compose.dev.yml build
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d api dashboard spark-streaming
```

### Thứ tự thực hiện

1. Tạo 4 Dockerfiles riêng biệt
2. Tạo `.dockerignore`
3. Tạo `docker-compose.yml` (production)
4. Tạo `docker-compose.dev.yml`
5. Tạo `Makefile`
6. Test build: `make build`
7. Test dev: `docker compose -f docker-compose.yml -f docker-compose.dev.yml build && up -d` hoặc 
`docker compose -f docker-compose.dev.yml up -d`
8. Push khi ổn định: `make build-push`

---

## Changelog

| Version | Date | Description |
|---------|------|-------------|
| v1 | 2026-05-17 | Docker optimization proposal (v1.2) |