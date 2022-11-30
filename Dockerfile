FROM ubuntu:18.04
MAINTAINER Ridwan Shariffdeen <ridwan@comp.nus.edu.sg>
ARG DEBIAN_FRONTEND=noninteractive
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
RUN apt-get update && apt-get upgrade -y && apt-get autoremove -y
RUN apt-get install -y --no-install-recommends  \
       git \
       nano \
       ninja-build \
       pkg-config \
       protobuf-compiler-grpc \
       python \
       python3 \
       python3-pip \
       software-properties-common \
       unzip \
       vim \
       wget \
       zlib1g \
       zlib1g-dev

RUN python3 -m pip install --upgrade pip
RUN python3 -m pip --disable-pip-version-check --no-cache-dir install setuptools
RUN python3 -m pip --disable-pip-version-check --no-cache-dir install pylint
RUN python3 -m pip --disable-pip-version-check --no-cache-dir install cython
RUN python3 -m pip --disable-pip-version-check --no-cache-dir install pysmt==0.9.0
RUN pysmt-install --z3 --confirm-agreement
RUN python3 -m pip --disable-pip-version-check --no-cache-dir install funcy
RUN python3 -m pip --disable-pip-version-check --no-cache-dir install six
RUN python3 -m pip --disable-pip-version-check --no-cache-dir install wllvm; return 0;
RUN python3 -m pip --disable-pip-version-check --no-cache-dir install sympy

ADD . /opt/evoRepair
WORKDIR /opt/evoRepair
RUN git submodule update --init --recursive
RUN ln -s /opt/evoRepair/bin/evorepair /usr/bin/evorepair
RUN evorepair --help

