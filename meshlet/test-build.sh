#!/bin/bash
# Simple build test script for Meshlet

set -e

echo "🧪 Testing Meshlet build..."

# Test TypeScript compilation
echo "📦 Installing dependencies..."
npm install

echo "🔨 Building TypeScript..."
npm run build

echo "✅ TypeScript build successful"

# Test Docker build
echo "🐳 Building Docker image..."
docker build -t manifold/meshlet .

echo "✅ Docker build successful"

# Test basic config validation
echo "🔧 Testing configuration..."
node -e "
import { loadConfig } from './dist/config.js';
try {
  process.env.GATE_URL = 'ws://test:8777';
  const config = loadConfig();
  console.log('✅ Configuration loaded successfully');
  console.log('Agent name:', config.agentName);
  console.log('Capabilities:', config.capabilities);
} catch (error) {
  console.error('❌ Configuration test failed:', error.message);
  process.exit(1);
}
"

echo "🎉 All tests passed!"
echo ""
echo "To run a single Meshlet:"
echo "  docker run -e GATE_URL=ws://your-gate:8777 manifold/meshlet"
echo ""
echo "To run 10 Meshlets:"
echo "  cd meshlet && docker compose up"