import type { Identity, QueryOptions, AgentResult, WorkRequest, RouteOptions } from '../shared/types.js'

export interface ManifoldClientConfig {
  /**
   * Federation server addresses to connect to.
   * e.g. ['ws://trillian:8766', 'ws://hog:8766']
   */
  servers: string[]

  /**
   * This client's identity on the mesh.
   */
  identity: Identity

  /**
   * Milliseconds between reconnect attempts. Default 5000.
   */
  reconnectDelay?: number

  /**
   * Maximum reconnect attempts per server. Default Infinity.
   */
  maxReconnectAttempts?: number

  /**
   * Default query timeout in milliseconds. Default 10000.
   */
  defaultQueryTimeout?: number

  /**
   * Whether to log debug info. Default false.
   */
  debug?: boolean
}

export interface PendingRequest {
  resolve: (value: AgentResult[]) => void
  reject: (err: Error) => void
  timer: ReturnType<typeof setTimeout>
}

export interface PendingWorkRequest {
  resolve: (value: unknown) => void
  reject: (err: Error) => void
  timer: ReturnType<typeof setTimeout>
}

export type { Identity, QueryOptions, AgentResult, WorkRequest, RouteOptions }
