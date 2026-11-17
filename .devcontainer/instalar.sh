#!/usr/bin/env bash
# Instala todo lo necesario para la demo dentro de GitHub Codespaces (se ejecuta una sola vez al crear el codespace).
set -e

echo "== 1/3 Ollama =="
sudo apt-get update -y && sudo apt-get install -y zstd
curl -fsSL https://ollama.com/install.sh | sh
nohup ollama serve > /tmp/ollama.log 2>&1 &
sleep 5

echo "== 2/3 Dependencias de Python (CPU) =="
pip install --no-cache-dir torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu
pip install --no-cache-dir -r requirements-demo.txt

echo "== 3/3 Modelos =="
ollama pull qwen2.5:3b
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-small')"

echo "Listo. Ejecuta:  python src/app/demo.py --host 0.0.0.0"
