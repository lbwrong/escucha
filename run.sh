#!/bin/bash
# 一键启动：建虚拟环境、装依赖、启动服务（http://127.0.0.1:8765）
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
exec .venv/bin/python -u server.py
