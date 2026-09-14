#!/bin/bash
# Copy the Qwen3-0.6B snapshot out of the WSL HF cache (dereferencing symlinks)
# into the Windows project dir so the native Windows helper can load it offline.
set -e
snap=$(ls -d ~/.cache/huggingface/hub/models--Qwen--Qwen3-0.6B/snapshots/*/ | head -1)
dst=/mnt/c/claude/trilingual-ime/llm/models/Qwen3-0.6B
echo "snapshot: $snap"
mkdir -p "$dst"
cp -rL "$snap"/. "$dst"/
ls -la "$dst"
