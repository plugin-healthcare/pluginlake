# basic python3 image as base
FROM harbor2.vantage6.ai/infrastructure/algorithm-base

# This is a placeholder that should be overloaded by invoking
# docker build with '--build-arg PKG_NAME=...'
ARG PKG_NAME="http-folder-test"

# install federated algorithm
COPY . /app
RUN pip install /app
RUN echo 1 > /usr/local/lib/python3.10/site-packages/vantage6/algorithm/client/__build__

# Set environment variable to make name of the package available within the
# docker image.
ENV PKG_NAME=${PKG_NAME}

RUN apt-get update && \
    apt-get install -y nano curl
# Tell docker to execute `wrap_algorithm()` when the image is run. This function
# will ensure that the algorithm method is called properly.
CMD python -c "from vantage6.algorithm.tools.wrap import wrap_algorithm; wrap_algorithm()"
