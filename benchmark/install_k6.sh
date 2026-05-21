#!/bin/bash
# Cai dat k6 (Grafana load testing tool) - single binary

set -e

if command -v k6 &> /dev/null; then
    echo "k6 already installed: $(k6 version)"
    exit 0
fi

echo "Installing k6..."
wget -q https://github.com/grafana/k6/releases/latest/download/k6-linux-amd64.tar.gz
tar xzf k6-linux-amd64.tar.gz
sudo mv k6-v*/k6 /usr/local/bin/
rm -rf k6-*

echo "k6 $(k6 version) installed to /usr/local/bin/k6"
