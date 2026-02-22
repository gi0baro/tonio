#!/usr/bin/env bash

rm -rf ./bench/.venv
rm -rf ./target
mkdir -p ./bench/.venv
uv venv -p 3.14t ./bench/.venv

uv sync --group build

uv run maturin build --release --interpreter ./bench/.venv/bin/python
VIRTUAL_ENV=$(pwd)/bench/.venv uv pip install $(ls target/wheels/tonio-*-cp314-*.whl)
VIRTUAL_ENV=$(pwd)/bench/.venv uv pip install numpy trio tinyio

cd ./bench

# base bench
BENCHMARK_EXC_PREFIX=$(pwd)/.venv/bin ./.venv/bin/python benchmarks.py 1m
mv ./results/data.json ./results/1m.json

# net bench
BENCHMARK_EXC_PREFIX=$(pwd)/.venv/bin ./.venv/bin/python benchmarks.py net_sock
mv ./results/data.json ./results/net.json

# concurrency
BENCHMARK_EXC_PREFIX=$(pwd)/.venv/bin ./.venv/bin/python benchmarks.py concurrency
mv ./results/data.json ./results/concurrency.json
