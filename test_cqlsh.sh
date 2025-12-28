#!/bin/bash

# Get credentials from .env
source .env

# Connect to cqlsh
cqlsh \
  -u "$SCYLLADB_USERNAME" \
  -p "$SCYLLADB_PASSWORD" \
  ${SCYLLADB_HOSTS%%,*} \
  $SCYLLADB_PORT \
  -k rag_demo \
  "$@"
