.PHONY: dist
dist:
	python3 setup.py sdist
	rm -rf vocodiaSwitchServices.egg-info

.PHONY: clean
clean:
	rm -rf dist
	rm -rf vocodiaSwitchServices.egg-info

.PHONY: buildbase
buildbase:
	sudo docker build -t vocodiaswitchbase -f Dockerfile.base .

.PHONY: switch-push-dev
switch-push-dev:
	docker tag vocodia_switch_dev thedarkside362/vocodia_switch_dev:1.0.0
	docker push thedarkside362/vocodia_switch_dev:1.0.0

.PHONY: switch-base-push
switch-base-push:
	docker tag vocodiaswitchbase thedarkside362/vocodiaswitchbase:1.0
	docker push thedarkside362/vocodiaswitchbase:1.0

.PHONY: buildswitch-local
buildswitchbase-local:
	sudo docker build -t buildswitchbase -f Dockerfile.dev .

.PHONY: buildswitch-dev
buildswitch-dev:
	sudo docker buildx build -t vocodia_switch_dev -f Dockerfile.dev .


.PHONY: buildswitch-prod
buildswitchbase-prod:
	sudo docker buildx build -t switchbase_prod -f Dockerfile.dev .

.PHONY: switch-push-prod
switch-push-prod:
	docker tag switchbase_prod thedarkside362/switchbase_prod:1.0.0
	docker push thedarkside362/buildswitchbase_prod:1.0.0

.PHONY: build-and-push-dev
build-and-push-dev:
	make dist
	make buildswitch-dev
	make switch-push-dev

.PHONY: deploy-dev
deploy-dev:
    sudo docker pull thedarkside362/vocodia_switch_dev:1.0.0
	docker-compose -f etc/docker-compose-dev.yml