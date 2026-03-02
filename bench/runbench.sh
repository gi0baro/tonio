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

BENCHMARK_EXC_PREFIX=$(pwd)/.venv/bin ./.venv/bin/python benchmarks.py all
mv ./results/data.json ./results/all.json
