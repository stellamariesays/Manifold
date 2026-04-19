/**
 * Meshlet Message Responder
 * Handles incoming mesh messages and generates appropriate responses
 */

import type { MeshletConfig } from './config.js'

export interface MeshMessage {
  type: string
  [key: string]: any
}

export interface ResponseContext {
  agentName: string
  capabilities: string[]
  hubName: string
  meshId: string
}

export class MessageResponder {
  private config: MeshletConfig
  private context: ResponseContext

  constructor(config: MeshletConfig, context: ResponseContext) {
    this.config = config
    this.context = context
  }

  /**
   * Handle an incoming message and generate a response
   */
  async handleMessage(message: MeshMessage): Promise<MeshMessage | null> {
    switch (message.type) {
      case 'ping':
        return this.handlePing(message)
      
      case 'capability_query':
        return this.handleCapabilityQuery(message)
      
      case 'agent_request':
        return this.handleAgentRequest(message)
      
      default:
        return this.handleGenericMessage(message)
    }
  }

  private handlePing(message: MeshMessage): MeshMessage {
    return {
      type: 'pong',
      requestId: message.requestId,
      timestamp: new Date().toISOString(),
      sender: this.context.meshId
    }
  }

  private handleCapabilityQuery(message: MeshMessage): MeshMessage {
    const matchesCapability = !message.capability || 
      this.context.capabilities.includes(message.capability)

    if (matchesCapability) {
      return {
        type: 'capability_response',
        requestId: message.requestId,
        agents: [{
          name: this.context.agentName,
          hub: this.context.hubName,
          capabilities: this.context.capabilities,
          pressure: 0.1,
          lastSeen: new Date().toISOString(),
          isLocal: false
        }],
        timestamp: new Date().toISOString(),
        sender: this.context.meshId
      }
    }

    return {
      type: 'capability_response',
      requestId: message.requestId,
      agents: [],
      timestamp: new Date().toISOString(),
      sender: this.context.meshId
    }
  }

  private async handleAgentRequest(message: MeshMessage): Promise<MeshMessage> {
    const { task, requestId } = message
    
    if (!task) {
      return {
        type: 'agent_response',
        requestId,
        success: false,
        error: 'No task provided',
        timestamp: new Date().toISOString(),
        sender: this.context.meshId
      }
    }

    // Handle different task types
    let result: any
    let success = true
    let error: string | undefined

    try {
      switch (task.type) {
        case 'ping':
          result = { message: 'pong', agent: this.context.agentName }
          break
          
        case 'status':
          result = {
            agent: this.context.agentName,
            hub: this.context.hubName,
            capabilities: this.context.capabilities,
            uptime: process.uptime(),
            timestamp: new Date().toISOString()
          }
          break
          
        case 'capability_challenge':
          result = await this.handleCapabilityChallenge(task)
          break
          
        default:
          if (this.config.llmMode === 'groq') {
            result = await this.handleWithGroq(task)
          } else {
            result = {
              message: `Meshlet ${this.context.agentName} received your ${task.type || 'unknown'} message`,
              agent: this.context.agentName,
              echo: task
            }
          }
      }
    } catch (err) {
      success = false
      error = err instanceof Error ? err.message : 'Unknown error'
    }

    return {
      type: 'agent_response',
      requestId,
      success,
      result,
      error,
      timestamp: new Date().toISOString(),
      sender: this.context.meshId
    }
  }

  private async handleCapabilityChallenge(task: any): Promise<any> {
    const { capability, challenge } = task
    
    if (!this.context.capabilities.includes(capability)) {
      throw new Error(`Capability ${capability} not supported`)
    }

    // Generate a fake capability proof
    return {
      capability,
      challenge,
      proof: `meshlet-proof-${capability}-${Date.now()}`,
      agent: this.context.agentName,
      verified: true,
      confidence: 0.95
    }
  }

  private async handleWithGroq(task: any): Promise<any> {
    if (!this.config.groqApiKey) {
      throw new Error('Groq API key not configured')
    }

    try {
      const response = await fetch('https://api.groq.com/openai/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${this.config.groqApiKey}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          model: 'mixtral-8x7b-32768',
          messages: [
            {
              role: 'system',
              content: `You are ${this.context.agentName}, a lightweight test agent in the Manifold mesh network. You have capabilities: ${this.context.capabilities.join(', ')}. Respond concisely and helpfully.`
            },
            {
              role: 'user',
              content: `Task: ${task.type || 'unknown'}\nDetails: ${JSON.stringify(task, null, 2)}`
            }
          ],
          max_tokens: 500,
          temperature: 0.7
        })
      })

      if (!response.ok) {
        throw new Error(`Groq API error: ${response.statusText}`)
      }

      const data = await response.json()
      const content = data.choices?.[0]?.message?.content || 'No response from LLM'

      return {
        llm_response: content,
        agent: this.context.agentName,
        model: 'mixtral-8x7b-32768',
        task_echo: task
      }
    } catch (err) {
      return {
        message: `Meshlet ${this.context.agentName} received your ${task.type || 'unknown'} message`,
        agent: this.context.agentName,
        llm_error: err instanceof Error ? err.message : 'Unknown LLM error',
        echo: task
      }
    }
  }

  private async handleGenericMessage(message: MeshMessage): Promise<MeshMessage | null> {
    // For most message types, we don't respond (just log)
    if (['mesh_sync', 'mesh_delta', 'peer_announce', 'peer_bye'].includes(message.type)) {
      return null
    }

    // For unknown message types, respond with echo if LLM enabled
    if (this.config.llmMode === 'groq') {
      try {
        const llmResponse = await this.handleWithGroq({ type: message.type, data: message })
        return {
          type: 'generic_response',
          originalType: message.type,
          requestId: message.requestId,
          response: llmResponse,
          timestamp: new Date().toISOString(),
          sender: this.context.meshId
        }
      } catch (err) {
        // Fall through to simple response
      }
    }

    return {
      type: 'generic_response',
      originalType: message.type,
      requestId: message.requestId,
      response: {
        message: `Meshlet ${this.context.agentName} received ${message.type} message`,
        agent: this.context.agentName
      },
      timestamp: new Date().toISOString(),
      sender: this.context.meshId
    }
  }
}