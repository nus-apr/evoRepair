FROM ubuntu:18.04 as intermediate
RUN apt-get update
RUN apt-get install -y git

ARG SSH_KEY
RUN mkdir ~/.ssh
RUN echo "${SSH_KEY}" > ~/.ssh/id_rsa
RUN chmod 600 ~/.ssh/id_rsa
RUN printf "%s" "github.com ssh-rsa " \
    "AAAAB3NzaC1yc2EAAAABIwAAAQEAq2A7hRGmdnm9tUDbO9IDSwBK6TbQa+PXYPCPy6rbTrTtw7PHkccKrpp0yVhp5HdEIcKr6pLlVDB" \
    "fOLX9QUsyCOV0wzfjIJNlGEYsdlLJizHhbn2mUjvSAHQqZETYP81eFzLQNnPHt4EVVUh7VfDESU84KezmD5QlWpXLmvU31/yMf+Se8" \
    "xhHTvKSCZIFImWwoG6mbUoWf9nzpIoaSjB+weqqUUmpaaasXVal72J+UX2B+2RPW3RcT0eOzQgqlJL3RKrTJvdsjE3JEAvGq3lGHSZXy28G3" \
    "skua2SmVi/w4yCE6gbODqnTWlg7+wC604ydGXA8VJiS5ap43JXiUFFAaQ==" >> ~/.ssh/known_hosts \
    && printf "\n" >> ~/.ssh/known_hosts

# University firewall blocks SSH, so use SSH over HTTPS
RUN printf "%s" "ssh.github.com ecdsa-sha2-nistp256 " \
    "AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87uRgg6CLrbo5wAdT" \
    "/y6v0mKV0U2w0WZ2YB/++Tpockg=" >> ~/.ssh/known_hosts \
    && printf "\n" >> ~/.ssh/known_hosts
RUN printf "Host github.com\n\tHostname ssh.github.com\n\tPort 443\n\tUser git\n" >> ~/.ssh/config

ADD . /opt/EvoRepair
WORKDIR /opt/EvoRepair
RUN git submodule update --init --recursive --remote

FROM ubuntu:18.04
MAINTAINER Ridwan Shariffdeen <ridwan@comp.nus.edu.sg>
ARG DEBIAN_FRONTEND=noninteractive
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
RUN apt-get update && apt-get upgrade -y && apt-get autoremove -y
RUN apt-get install -y --no-install-recommends  \
       ant \
       git \
       nano \
       ninja-build \
       openjdk-8-jdk \
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

# Install Maven
RUN cd /opt && wget https://mirrors.estointernet.in/apache/maven/maven-3/3.6.3/binaries/apache-maven-3.6.3-bin.tar.gz && \
    tar -xvf apache-maven-3.6.3-bin.tar.gz
ENV M2_HOME '/opt/apache-maven-3.6.3'
ENV PATH "$M2_HOME/bin:${PATH}"

#ADD . /opt/EvoRepair
COPY --from=intermediate /opt/EvoRepair /opt/EvoRepair
WORKDIR /opt/EvoRepair
# RUN git submodule update --init --recursive
RUN ln -s /opt/EvoRepair/bin/evorepair /usr/bin/evorepair
RUN evorepair --help

# Build ARJA
WORKDIR /opt/EvoRepair/extern/arja
RUN mvn clean package
WORKDIR /opt/EvoRepair/extern/arja/external
RUN rm -r bin; mkdir bin; javac -cp lib/*: -d bin $(find src -name '*.java')

# Build Defects4J (adapted from https://github.com/rjust/defects4j/blob/master/Dockerfile)
RUN \
  apt-get update -y && \
  apt-get install software-properties-common -y && \
  apt-get update -y && \
  apt-get install -y openjdk-8-jdk \
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

WORKDIR /opt/EvoRepair