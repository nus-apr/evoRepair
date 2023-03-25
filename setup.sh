#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
EXTERN_DIR=${SCRIPT_DIR}/extern

echo "Setting up ARJA..."
ARJA_DIR=${EXTERN_DIR}/arja
(set -x; cd ${ARJA_DIR}; mvn clean package -DskipTests -q)
(set -x; cd ${ARJA_DIR}/external; ant clean compile -silent)
echo -e "Done.\n"

echo "Setting up EvoSuite..."
(set -x; cd ${EXTERN_DIR}/evosuite; mvn clean package -DskipTests -q)
echo -e "Done.\n"

echo "Setting up oracle parser..."
(set -x; cd ${EXTERN_DIR}/oracle-parser; mvn clean package -DskipTests -q)
echo -e "Done.\n"

echo "Setting up validator..."
(set -x; cd ${EXTERN_DIR}/plain-validator; mvn clean package -DskipTests -q)
echo -e "Done.\n"

echo "EvoRepair successfully set up."
