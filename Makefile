ifneq (,$(wildcard .env))
	include .env
	export
endif

DOCKER_USERNAME ?= otto
TAG ?= $(DOCKER_TAG)
TAG ?= latest
build:
	docker build -f Dockerfile.api -t $(DOCKER_USERNAME)/otto-api:$(TAG) .
	docker build -f Dockerfile.streaming -t $(DOCKER_USERNAME)/otto-spark-streaming:$(TAG) .
	docker build -f Dockerfile.dashboard -t $(DOCKER_USERNAME)/otto-dashboard:$(TAG) .
	docker build -f Dockerfile.setup -t $(DOCKER_USERNAME)/otto-setup:$(TAG) .
	docker build -f Dockerfile.spark-worker -t $(DOCKER_USERNAME)/otto-spark-worker:$(TAG) .
	docker build -f Dockerfile.frontend --target production -t $(DOCKER_USERNAME)/otto-frontend:$(TAG) .

build-api:
	docker build -f Dockerfile.api -t $(DOCKER_USERNAME)/otto-api:$(TAG) .

build-streaming:
	docker build -f Dockerfile.streaming -t $(DOCKER_USERNAME)/otto-spark-streaming:$(TAG) .


build-dashboard:
	docker build -f Dockerfile.dashboard -t $(DOCKER_USERNAME)/otto-dashboard:$(TAG) .

build-setup:
	docker build -f Dockerfile.setup -t $(DOCKER_USERNAME)/otto-setup:$(TAG) .

build-frontend:
	docker build -f Dockerfile.frontend --target production -t $(DOCKER_USERNAME)/otto-frontend:$(TAG) .


push:
	docker push $(DOCKER_USERNAME)/otto-api:$(TAG)
	docker push $(DOCKER_USERNAME)/otto-spark-streaming:$(TAG)
	docker push $(DOCKER_USERNAME)/otto-dashboard:$(TAG)
	docker push $(DOCKER_USERNAME)/otto-setup:$(TAG)
	docker push $(DOCKER_USERNAME)/otto-frontend:$(TAG)

build-push: build push

build-dev:
	docker build -f Dockerfile.api -t $(DOCKER_USERNAME)/otto-api:$(TAG)-dev .
	docker build -f Dockerfile.streaming -t $(DOCKER_USERNAME)/otto-spark-streaming:$(TAG)-dev .
	docker build -f Dockerfile.dashboard -t $(DOCKER_USERNAME)/otto-dashboard:$(TAG)-dev .
	docker build -f Dockerfile.frontend --target dev -t $(DOCKER_USERNAME)/otto-frontend:$(TAG)-dev .

build-spark-worker:
	docker build -f Dockerfile.spark-worker -t $(DOCKER_USERNAME)/otto-spark-worker:$(TAG) .

clean:
	docker rmi \
		$(DOCKER_USERNAME)/otto-api:$(TAG) \
		$(DOCKER_USERNAME)/otto-spark-streaming:$(TAG) \
		$(DOCKER_USERNAME)/otto-dashboard:$(TAG) \
		$(DOCKER_USERNAME)/otto-setup:$(TAG) \
		$(DOCKER_USERNAME)/otto-spark-worker:$(TAG) \
		$(DOCKER_USERNAME)/otto-frontend:$(TAG) 2>/dev/null || true

clean-all: clean
	docker rmi \
		$(DOCKER_USERNAME)/otto-api:$(TAG)-dev \
		$(DOCKER_USERNAME)/otto-spark-streaming:$(TAG)-dev \
		$(DOCKER_USERNAME)/otto-dashboard:$(TAG)-dev \
		$(DOCKER_USERNAME)/otto-frontend:$(TAG)-dev 2>/dev/null || true

.PHONY: build push build-push build-dev clean clean-all build-api build-streaming build-dashboard build-setup build-frontend build-spark-worker