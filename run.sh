#!/bin/bash
cd "$(dirname "$0")"
source ~/.venv/lynn-view/bin/activate
uvicorn main:app --host 127.0.0.1 --port 8000
