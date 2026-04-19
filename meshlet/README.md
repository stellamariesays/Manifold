# Meshlet - Lightweight Test Agent for Manifold

Meshlet is a lightweight, Docker-ready test agent designed to simulate mesh agents for testing Phase 1 of the Manifold project (MeshPass identity + The Gate WebSocket gateway).

## Features

- 🔐 **MeshPass Identity**: Generates Ed25519 keypairs for cryptographic authentication
- 🌐 **Gate Connection**: Connects to The Gate WebSocket gateway with signed auth
- 🏓 **Protocol Support**: Responds to PING/PONG, capability queries, and agent requests
- 🤖 **Optional LLM**: Integrates with Groq API for intelligent responses
- 🐳 **Docker Ready**: Minimal Alpine-based container for easy deployment
- 📊 **Structured Logging**: JSON-formatted logs for monitoring and debugging
- 🔄 **Auto-Reconnect**: Exponential backoff reconnection with configurable limits

## Quick Start

### Prerequisites

- Docker and Docker Compose
- A running instance of The Gate (WebSocket server)
- Optional: Groq API key for LLM responses

### 1. Build the Container

```bash
docker build -t manifold/meshlet meshlet/
```

### 2. Run a Single Agent

```bash
docker run -e GATE_URL=ws://your-gate:8777 -e AGENT_NAME=test-01 manifold/meshlet
```

### 3. Run 10 Agents with Docker Compose

```bash
cd meshlet
docker compose up
```

### 4. Scale to 50 Agents

```bash
docker compose up --scale meshlet-01=50
```

Or distribute across multiple services:

```bash
docker compose up --scale meshlet-01=10 --scale meshlet-02=10 --scale meshlet-03=10 --scale meshlet-04=10 --scale meshlet-05=10
```

## Configuration

Meshlet is configured entirely through environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GATE_URL` | ✅ | - | WebSocket URL of The Gate (e.g., `ws://localhost:8777`) |
| `AGENT_NAME` | ❌ | `meshlet-XXXX` | Display name for this agent |
| `CAPABILITIES` | ❌ | `ping,test` | Comma-separated list of capabilities |
| `HUB_NAME` | ❌ | `meshlet-hub` | Hub name to register as |
| `LOG_LEVEL` | ❌ | `info` | Logging level: `debug`, `info`, `warn`, `error` |
| `LLM_MODE` | ❌ | `none` | LLM integration: `none` or `groq` |
| `GROQ_API_KEY` | ❌ | - | Required if `LLM_MODE=groq` |
| `RECONNECT_DELAY_MS` | ❌ | `5000` | Base reconnection delay in milliseconds |
| `MAX_RECONNECT_ATTEMPTS` | ❌ | `0` | Max reconnection attempts (0 = infinite) |

### Examples

#### Basic Agent
```bash
docker run \
  -e GATE_URL=ws://gate.manifold.org:8777 \
  -e AGENT_NAME=test-agent-01 \
  manifold/meshlet
```

#### Agent with LLM Support
```bash
docker run \
  -e GATE_URL=ws://gate.manifold.org:8777 \
  -e AGENT_NAME=smart-agent-01 \
  -e LLM_MODE=groq \
  -e GROQ_API_KEY=gsk_... \
  -e CAPABILITIES=ping,test,chat,analysis \
  manifold/meshlet
```

#### Debug Mode
```bash
docker run \
  -e GATE_URL=ws://localhost:8777 \
  -e AGENT_NAME=debug-agent \
  -e LOG_LEVEL=debug \
  manifold/meshlet
```

## Protocol Support

Meshlet supports the following mesh protocol messages:

### Core Messages
- **ping** → **pong**: Basic connectivity test
- **capability_query** → **capability_response**: Capability discovery
- **agent_request** → **agent_response**: Task execution

### Task Types
- **ping**: Returns a pong response
- **status**: Returns agent status and capabilities
- **capability_challenge**: Generates fake capability proofs for testing

### LLM Integration (Groq)
When `LLM_MODE=groq`, unknown messages are forwarded to the Groq API for intelligent responses using the Mixtral model.

## Development

### Local Development

```bash
cd meshlet
npm install
npm run dev
```

### Building

```bash
npm run build
npm start
```

### Testing with Real Gate

1. Start a local Manifold federation server with The Gate
2. Update `GATE_URL` to point to your gate instance
3. Run Meshlet and watch the logs for authentication and message flow

## Docker Image Details

- **Base**: `node:22-alpine`
- **Size**: ~80MB (optimized multi-stage build)
- **User**: Runs as non-root user `meshlet`
- **Health Check**: Process-based health monitoring
- **Resource Limits**: 128MB RAM, 0.25 CPU by default

## Monitoring and Logging

All logs are output as structured JSON to stdout for easy parsing:

```json
{
  "timestamp": "2024-04-19T10:30:00.000Z",
  "level": "info",
  "message": "Authentication successful",
  "agent": "meshlet-01",
  "meshId": "meshlet-01@meshlet-hub#a1b2c3d4",
  "hub": "meshlet-hub"
}
```

Health status is logged every minute at debug level, including:
- Connection status
- Authentication status
- Message counts
- Memory usage
- Last activity timestamp

## Architecture Notes

### MeshPass Generation
Each Meshlet generates a fresh Ed25519 keypair on startup. The MeshID format is:
```
{agentName}@{hubName}#{fingerprint}
```

### Authentication Flow
1. Connect to The Gate WebSocket
2. Receive `gate_info` message
3. Send `mesh_auth` with signed challenge
4. Receive `auth_success` confirmation
5. Start sending/receiving mesh protocol messages

### Reconnection Strategy
- Exponential backoff with jitter
- Base delay configurable via `RECONNECT_DELAY_MS`
- Maximum attempts configurable via `MAX_RECONNECT_ATTEMPTS`
- Automatic retry on connection failures

## Use Cases

### Load Testing
Scale to hundreds of agents to test Gate performance:
```bash
docker compose up --scale meshlet-01=100
```

### Protocol Testing
Test various mesh protocol scenarios with different capability configurations.

### Integration Testing
Validate MeshPass authentication and message routing through The Gate.

### Development Environment
Simulate a full mesh network locally for development and debugging.

## Troubleshooting

### Common Issues

#### Connection Refused
- Verify `GATE_URL` is correct and The Gate is running
- Check network connectivity between container and Gate

#### Authentication Failed
- Ensure The Gate is accepting new MeshPass registrations
- Check logs for signature verification errors

#### High Memory Usage
- Reduce `LOG_LEVEL` from `debug` to `info`
- Monitor for message accumulation in responder

### Debug Mode
Set `LOG_LEVEL=debug` to see detailed message flow:
```bash
docker run -e LOG_LEVEL=debug -e GATE_URL=ws://localhost:8777 manifold/meshlet
```

## Contributing

Meshlet is designed to be lightweight and focused. When adding features:

1. Keep dependencies minimal
2. Maintain Docker image size under 100MB
3. Ensure all configuration is via environment variables
4. Add structured logging for new features
5. Update this README with any new configuration options

## License

MIT License - see the main Manifold project for details.