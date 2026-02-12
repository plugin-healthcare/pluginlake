# `make` is expected to be called from the directory that contains
# this Makefile

# PKG_NAME is based on the name of the folder that holds this code
# (i.e. the name of the directory that contains 'src')
# $(eval PKG_NAME := $(shell Rscript -e "cat(basename(getwd()))"))
# PKG_NAME = "v6example"

# These variables can be set as environment variables or as arguments to `make`
# HOST ?= harbor2.vantage6.ai
HOST ?= drplugindhdprd.azurecr.io
IMAGE ?= v6-http-test
TAG ?= latest
$(eval PWD := $(shell Rscript -e "cat(getwd())"))


echo:
	@echo "package name: ${PKG_NAME}"
	@echo "  image name: ${IMAGE}"
	@echo "         tag: ${TAG}"
	@echo "         pwd: ${PWD}"
	@echo ""


docker-image:
	@echo "************************************************************************"
	@echo "* Building image '${IMAGE}:${TAG}' "
	@echo "************************************************************************"

	# Build the docker image containing the local algorithm
	# docker build --no-cache -f ./Dockerfile -t $IMAGE:$TAG -t $HOST/$IMAGE:$TAG .
	docker build --no-cache \
	-f ./Dockerfile \
	-t v6-http-tag \
	-t  drplugindhdprd.azurecr.io/v6-http-tag:latest \
	./
