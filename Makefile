COMPOSE := docker compose
TAG ?= latest
IMAGE_REPO ?= ghcr.io/ttww/flatmanager
VITE_API_BASE_URL ?= http://localhost:8000
ADMIN_BASE_PATH ?= /admin/
GUEST_BASE_PATH ?= /guest/
DOCS_URL ?= /api/docs
REDOC_URL ?= /api/redoc
OPENAPI_URL ?= /api/openapi.json

.PHONY: build up down restart logs ps push publish pull

build:
	IMAGE_REPO=$(IMAGE_REPO) TAG=$(TAG) VITE_API_BASE_URL=$(VITE_API_BASE_URL) ADMIN_BASE_PATH=$(ADMIN_BASE_PATH) GUEST_BASE_PATH=$(GUEST_BASE_PATH) DOCS_URL=$(DOCS_URL) REDOC_URL=$(REDOC_URL) OPENAPI_URL=$(OPENAPI_URL) $(COMPOSE) build

up:
	IMAGE_REPO=$(IMAGE_REPO) TAG=$(TAG) VITE_API_BASE_URL=$(VITE_API_BASE_URL) ADMIN_BASE_PATH=$(ADMIN_BASE_PATH) GUEST_BASE_PATH=$(GUEST_BASE_PATH) DOCS_URL=$(DOCS_URL) REDOC_URL=$(REDOC_URL) OPENAPI_URL=$(OPENAPI_URL) $(COMPOSE) up

upd:
	IMAGE_REPO=$(IMAGE_REPO) TAG=$(TAG) VITE_API_BASE_URL=$(VITE_API_BASE_URL) ADMIN_BASE_PATH=$(ADMIN_BASE_PATH) GUEST_BASE_PATH=$(GUEST_BASE_PATH) DOCS_URL=$(DOCS_URL) REDOC_URL=$(REDOC_URL) OPENAPI_URL=$(OPENAPI_URL) $(COMPOSE) up -d

prod-up:
	VITE_API_BASE_URL=https://experiments.thomaswelsch.de ADMIN_BASE_PATH=/admin/ GUEST_BASE_PATH=/guest/ DOCS_URL=/api/docs REDOC_URL=/api/redoc OPENAPI_URL=/api/openapi.json $(MAKE) build up

prod-upd:
	VITE_API_BASE_URL=https://experiments.thomaswelsch.de ADMIN_BASE_PATH=/admin/ GUEST_BASE_PATH=/guest/ DOCS_URL=/api/docs REDOC_URL=/api/redoc OPENAPI_URL=/api/openapi.json $(MAKE) build upd

down:
	$(COMPOSE) down

restart: down up

logs:
	$(COMPOSE) logs -f --tail=200

ps:
	$(COMPOSE) ps

push:
	IMAGE_REPO=$(IMAGE_REPO) TAG=$(TAG) $(COMPOSE) push

publish: build push

pull:
	git pull
