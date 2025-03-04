#!/bin/bash
wget https://dist.ipfs.tech/kubo/v0.33.1/kubo_v0.33.1_linux-amd64.tar.gz && \
  tar -xvzf kubo_v0.33.1_linux-amd64.tar.gz && \
  cd kubo && \
  bash install.sh
ipfs init
ipfs config --json Swarm.EnableRelayHop true
cd ..
./write_key.sh

