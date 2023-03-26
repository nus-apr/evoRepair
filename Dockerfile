FROM ubuntu:18.04
MAINTAINER Ridwan Shariffdeen <ridwan@comp.nus.edu.sg>
ARG DEBIAN_FRONTEND=noninteractive
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
RUN apt-get update && apt-get upgrade -y && apt-get autoremove -y
RUN apt-get install -y --no-install-recommends  \
       git \
       vim \
       nano \
       ant \
       python \
       python3.8 \
       python3-distutils \
       unzip \
       wget \
       tmux

# install utility to transfrom dos to unix encodings and vice-versa
RUN apt-get install -y --no-install-recommends dos2unix

# set up python3.8
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.8 1
RUN update-alternatives --set python3 /usr/bin/python3.8
RUN wget -q -O /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py && cd /tmp && python3 get-pip.py
RUN python3 -m pip install unidiff

# Install Maven
RUN cd /opt && wget -q https://mirrors.estointernet.in/apache/maven/maven-3/3.6.3/binaries/apache-maven-3.6.3-bin.tar.gz && \
    tar -xvf apache-maven-3.6.3-bin.tar.gz
ENV M2_HOME '/opt/apache-maven-3.6.3'
ENV PATH "$M2_HOME/bin:${PATH}"

# Instead of openjdk-8-jdk, install zulu jdk 8.0 to accomodate Defects4J version 1.5.0 and older
RUN wget -q -O /tmp/zulu8.deb https://cdn.azul.com/zulu/bin/zulu8.66.0.15-ca-jdk8.0.352-linux_amd64.deb
RUN apt install -y /tmp/zulu8.deb

# Build Defects4J (adapted from https://github.com/rjust/defects4j/blob/master/Dockerfile)
# JDK already set up above, so dont install JDK here
RUN \
  apt-get update -y && \
  apt-get install software-properties-common -y --no-install-recommends && \
  apt-get update -y && \
  apt-get install -y --no-install-recommends \
                git \
                build-essential \
				subversion \
				perl \
				curl \
				unzip \
				cpanminus \
				make

RUN cd /opt && git clone https://github.com/rjust/defects4j.git
WORKDIR /opt/defects4j
RUN cpanm --installdeps .
RUN ./init.sh
ENV PATH="/opt/defects4j/framework/bin:${PATH}"

ADD ./defects4j.diff /tmp
RUN patch -p1 -i /tmp/defects4j.diff

ADD . /opt/EvoRepair
WORKDIR /opt/EvoRepair
RUN ./setup.sh
RUN ln -s /opt/EvoRepair/bin/evorepair /usr/bin/evorepair
RUN evorepair --help
