/**
 * Meshlet Configuration
 * Environment variable-based configuration for lightweight test agent
 */

export interface MeshletConfig {
  /** Display name for this agent (default: meshlet-XXXX where XXXX is random) */
  agentName: string
  
  /** WebSocket URL of The Gate (required) */
  gateUrl: string
  
  /** Comma-separated list of capabilities (default: "ping,test") */
  capabilities: string[]
  
  /** LLM mode: "none" (default) or "groq" */
  llmMode: 'none' | 'groq'
  
  /** Groq API key (required if LLM_MODE=groq) */
  groqApiKey?: string
  
  /** Hub name to register as (default: meshlet-hub) */
  hubName: string
  
  /** Log level: debug/info/warn (default: info) */
  logLevel: 'debug' | 'info' | 'warn'
  
  /** Reconnect delay base in milliseconds */
  reconnectDelayMs: number
  
  /** Maximum reconnect attempts (0 = infinite) */
  maxReconnectAttempts: number
}

function generateRandomId(): string {
  return Math.random().toString(36).substring(2, 6).toUpperCase()
}

export function loadConfig(): MeshletConfig {
  const config: MeshletConfig = {
    agentName: process.env.AGENT_NAME || `meshlet-${generateRandomId()}`,
    gateUrl: process.env.GATE_URL || (() => {
      throw new Error('GATE_URL environment variable is required')
    })(),
    capabilities: (process.env.CAPABILITIES || 'ping,test').split(',').map(c => c.trim()),
    llmMode: (process.env.LLM_MODE as 'none' | 'groq') || 'none',
    groqApiKey: process.env.GROQ_API_KEY,
    hubName: process.env.HUB_NAME || 'meshlet-hub',
    logLevel: (process.env.LOG_LEVEL as 'debug' | 'info' | 'warn') || 'info',
    reconnectDelayMs: parseInt(process.env.RECONNECT_DELAY_MS || '5000', 10),
    maxReconnectAttempts: parseInt(process.env.MAX_RECONNECT_ATTEMPTS || '0', 10)
  }
  
  // Validation
  if (config.llmMode === 'groq' && !config.groqApiKey) {
    throw new Error('GROQ_API_KEY is required when LLM_MODE=groq')
  }
  
  if (!config.gateUrl.startsWith('ws://') && !config.gateUrl.startsWith('wss://')) {
    throw new Error('GATE_URL must be a valid WebSocket URL (ws:// or wss://)')
  }
  
  return config
}

export function logConfigSafely(config: MeshletConfig): Record<string, any> {
  return {
    agentName: config.agentName,
    gateUrl: config.gateUrl,
    capabilities: config.capabilities,
    llmMode: config.llmMode,
    groqApiKey: config.groqApiKey ? '[REDACTED]' : undefined,
    hubName: config.hubName,
    logLevel: config.logLevel,
    reconnectDelayMs: config.reconnectDelayMs,
    maxReconnectAttempts: config.maxReconnectAttempts
  }
}