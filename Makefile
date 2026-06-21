COMPOSE := docker compose
TAG ?= latest
IMAGE_REPO ?= ghcr.io/ttww/flatmanager
VITE_API_BASE_URL ?= http://localhost:8000

.PHONY: build up down restart logs ps push publish

build:
	IMAGE_REPO=$(IMAGE_REPO) TAG=$(TAG) VITE_API_BASE_URL=$(VITE_API_BASE_URL) $(COMPOSE) build

up:
	IMAGE_REPO=$(IMAGE_REPO) TAG=$(TAG) VITE_API_BASE_URL=$(VITE_API_BASE_URL) $(COMPOSE) up

upd:
	IMAGE_REPO=$(IMAGE_REPO) TAG=$(TAG) VITE_API_BASE_URL=$(VITE_API_BASE_URL) $(COMPOSE) up -d

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
