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

push:
	docker push $(DOCKER_USERNAME)/otto-api:$(TAG)
	docker push $(DOCKER_USERNAME)/otto-spark-streaming:$(TAG)
	docker push $(DOCKER_USERNAME)/otto-dashboard:$(TAG)
	docker push $(DOCKER_USERNAME)/otto-setup:$(TAG)

build-push: build push

build-dev:
	docker build -f Dockerfile.api -t $(DOCKER_USERNAME)/otto-api:$(TAG)-dev .
	docker build -f Dockerfile.streaming -t $(DOCKER_USERNAME)/otto-spark-streaming:$(TAG)-dev .
	docker build -f Dockerfile.dashboard -t $(DOCKER_USERNAME)/otto-dashboard:$(TAG)-dev .

clean:
	docker rmi \
		$(DOCKER_USERNAME)/otto-api:$(TAG) \
		$(DOCKER_USERNAME)/otto-spark-streaming:$(TAG) \
		$(DOCKER_USERNAME)/otto-dashboard:$(TAG) \
		$(DOCKER_USERNAME)/otto-setup:$(TAG) 2>/dev/null || true

clean-all: clean
	docker rmi \
		$(DOCKER_USERNAME)/otto-api:$(TAG)-dev \
		$(DOCKER_USERNAME)/otto-spark-streaming:$(TAG)-dev \
		$(DOCKER_USERNAME)/otto-dashboard:$(TAG)-dev 2>/dev/null || true

.PHONY: build push build-push build-dev clean clean-all