#!/bin/bash
# Ollama setup script for VastAI instances
# This script installs Ollama and pulls a default model

set -e

echo "🚀 Starting Ollama setup..."

# Update system and install dependencies
echo "📦 Updating system packages..."
apt-get update > /dev/null 2>&1

# Install Ollama
echo "📥 Installing Ollama..."
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama service
echo "🔧 Starting Ollama service..."
systemctl start ollama
systemctl enable ollama

# Wait for Ollama to be ready
echo "⏳ Waiting for Ollama to be ready..."
for i in {1..30}; do
    if ollama list > /dev/null 2>&1; then
        echo "✅ Ollama is ready!"
        break
    fi
    echo -n "."
    sleep 2
done

# Pull a default model (llama3.2:3b as it's relatively small and capable)
echo "🤖 Pulling default model (llama3.2:3b)..."
ollama pull llama3.2:3b

# Verify the model is installed
echo "🔍 Verifying model installation..."
ollama list | grep llama3.2:3b

echo "🎉 Ollama setup complete!"
echo "💡 You can now use Ollama with: ollama run llama3.2:3b"
echo "🌐 Or access via API at http://localhost:11434"

# Keep the container running (Ollama runs as a service)
echo "💤 Ollama is running in the background. Container will remain alive."
while true; do
    sleep 60
done