#!/bin/bash

export USERNAME=$(echo "${RENKU_USERNAME:-user${RANDOM}}"|sed -e 's|@.*$||' -e 's|[^a-zA-Z0-9]|_|g')
export HADOOP_USER_NAME="${USERNAME}"

