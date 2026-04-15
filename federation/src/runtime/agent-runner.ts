/**
 * Agent Runner — executes agent scripts on behalf of the federation.
 *
 * Connects to the local federation WebSocket, listens for `task_request`
 * messages, spawns the matching agent script, captures JSON stdout,
 * and returns `task_result` through the federation.
 *
 * Usage:
 *   npx tsx src/runtime/agent-runner.ts \
 *     --config runner-config.json \
 *     --ws ws://localhost:8768
 */

import { WebSocket } from 'ws'
import { spawn, ChildProcess } from 'child_process'
import { readFileSync, watchFile } from 'fs'
import { argv } from 'process'

// ── Types (imported from protocol, duplicated here for standalone build) ────────

interface TaskRequest {
  id: string
  target: string
  capability?: string
  command: string
  args?: Record<string, unknown>
  timeout_ms?: number
  origin: string
  caller: string
  created_at: string
}

interface TaskResult {
  id: string
  status: 'success' | 'error' | 'timeout' | 'not_found' | 'rejected'
  output?: unknown
  error?: string
  executed_by?: string
  execution_ms?: number
  completed_at: string
}

interface TaskRequestMessage {
  type: 'task_request'
  task: TaskRequest
}

// ── Config ─────────────────────────────────────────────────────────────────────

interface AgentConfig {
  /** Agent name (must match atlas registration) */
  name: string
  /** Path to the executable script */
  script: string
  /** Working directory for the script */
  cwd?: string
  /** Environment variables to pass */
  env?: Record<string, string>
  /** Default timeout in ms (overrides global default) */
  timeout_ms?: number
  /** Max concurrent executions for this agent */
  maxConcurrency?: number
}

interface RunnerConfig {
  /** Hub name this runner belongs to */
  hub: string
  /** WebSocket URL of the local federation server */
  wsUrl: string
  /** Default task timeout in ms */
  defaultTimeoutMs: number
  /** Registered agents */
  agents: AgentConfig[]
}

// ── Runner ─────────────────────────────────────────────────────────────────────

interface RunningTask {
  task: TaskRequest
  process: ChildProcess
  startTime: number
  timeout: ReturnType<typeof setTimeout>
  stdout: Buffer[]
  stderr: Buffer[]
}

export class AgentRunner {
  private config: RunnerConfig
  private ws: WebSocket | null = null
  private runningTasks = new Map<string, RunningTask>()
  private agentConcurrency = new Map<string, number>()

  constructor(config: RunnerConfig) {
    this.config = config
  }

  async start(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.config.wsUrl)

      this.ws.on('open', () => {
        this.log(`Connected to federation at ${this.config.wsUrl}`)
        // Register as a task executor
        this.send({
          type: 'agent_runner_ready',
          hub: this.config.hub,
          agents: this.config.agents.map(a => a.name),
        })
        resolve()
      })

      this.ws.on('message', (data: Buffer) => {
        try {
          const msg = JSON.parse(data.toString())
          this.handleMessage(msg)
        } catch (err) {
          this.log(`Parse error: ${err}`)
        }
      })

      this.ws.on('close', () => {
        this.log('Disconnected from federation')
        this.reconnect()
      })

      this.ws.on('error', (err) => {
        this.log(`WebSocket error: ${err}`)
        reject(err)
      })
    })
  }

  private handleMessage(msg: Record<string, unknown>): void {
    if (msg.type === 'task_request') {
      const taskMsg = msg as unknown as TaskRequestMessage
      this.executeTask(taskMsg.task)
    }
  }

  private async executeTask(task: TaskRequest): Promise<void> {
    const agentName = task.target.includes('@')
      ? task.target.split('@')[0]
      : task.target

    // Find agent config
    const agentConfig = this.config.agents.find(a => a.name === agentName)
    if (!agentConfig) {
      this.sendResult({
        id: task.id,
        status: 'not_found',
        error: `Agent not found: ${agentName}`,
        executed_by: `${agentName}@${this.config.hub}`,
        completed_at: new Date().toISOString(),
      })
      return
    }

    // Check concurrency
    const current = this.agentConcurrency.get(agentName) ?? 0
    const maxConcurrency = agentConfig.maxConcurrency ?? 1
    if (current >= maxConcurrency) {
      this.sendResult({
        id: task.id,
        status: 'rejected',
        error: `Agent ${agentName} at max concurrency (${maxConcurrency})`,
        executed_by: `${agentName}@${this.config.hub}`,
        completed_at: new Date().toISOString(),
      })
      return
    }

    const timeoutMs = task.timeout_ms ?? agentConfig.timeout_ms ?? this.config.defaultTimeoutMs
    const startTime = Date.now()

    this.log(`Executing: ${agentName} ${task.command} (task ${task.id.substring(0, 8)}...)`)

    // Build args: script command [args_json]
    const args = [task.command]
    if (task.args && Object.keys(task.args).length > 0) {
      args.push(JSON.stringify(task.args))
    }

    const proc = spawn(agentConfig.script, args, {
      cwd: agentConfig.cwd,
      env: { ...process.env, ...agentConfig.env },
      stdio: ['pipe', 'pipe', 'pipe'],
    })

    const running: RunningTask = {
      task,
      process: proc,
      startTime,
      timeout: setTimeout(() => {
        this.log(`Timeout: ${agentName} (${timeoutMs}ms)`)
        proc.kill('SIGKILL')
      }, timeoutMs),
      stdout: [],
      stderr: [],
    }

    proc.stdout!.on('data', (chunk: Buffer) => running.stdout.push(chunk))
    proc.stderr!.on('data', (chunk: Buffer) => running.stderr.push(chunk))

    this.runningTasks.set(task.id, running)
    this.agentConcurrency.set(agentName, current + 1)

    // Send ack
    this.send({
      type: 'task_ack',
      task_id: task.id,
      queue_position: 0,
    })

    proc.on('close', (code) => {
      clearTimeout(running.timeout)
      this.runningTasks.delete(task.id)
      this.agentConcurrency.set(agentName, Math.max(0, current - 1))

      const executionMs = Date.now() - startTime
      const stdout = Buffer.concat(running.stdout).toString().trim()
      const stderr = Buffer.concat(running.stderr).toString().trim()

      if (code === 0 && stdout) {
        try {
          const output = JSON.parse(stdout)
          this.sendResult({
            id: task.id,
            status: 'success',
            output,
            executed_by: `${agentName}@${this.config.hub}`,
            execution_ms: executionMs,
            completed_at: new Date().toISOString(),
          })
          this.log(`Success: ${agentName} (${executionMs}ms)`)
        } catch {
          // stdout wasn't JSON — return as text
          this.sendResult({
            id: task.id,
            status: 'success',
            output: { text: stdout },
            executed_by: `${agentName}@${this.config.hub}`,
            execution_ms: executionMs,
            completed_at: new Date().toISOString(),
          })
        }
      } else {
        const errorMsg = stderr || `Process exited with code ${code}`
        this.sendResult({
          id: task.id,
          status: code === null ? 'timeout' : 'error',
          error: errorMsg,
          output: stdout ? { raw: stdout } : undefined,
          executed_by: `${agentName}@${this.config.hub}`,
          execution_ms: executionMs,
          completed_at: new Date().toISOString(),
        })
        this.log(`Error: ${agentName} — ${errorMsg} (${executionMs}ms)`)
      }
    })

    proc.on('error', (err) => {
      clearTimeout(running.timeout)
      this.runningTasks.delete(task.id)
      this.agentConcurrency.set(agentName, Math.max(0, current - 1))

      this.sendResult({
        id: task.id,
        status: 'error',
        error: err.message,
        executed_by: `${agentName}@${this.config.hub}`,
        execution_ms: Date.now() - startTime,
        completed_at: new Date().toISOString(),
      })
    })
  }

  private sendResult(result: TaskResult): void {
    this.send({ type: 'task_result', result })
  }

  private send(msg: Record<string, unknown>): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg))
    }
  }

  private reconnect(): void {
    setTimeout(() => {
      this.log('Reconnecting...')
      this.start().catch(() => this.reconnect())
    }, 5000)
  }

  private log(msg: string): void {
    console.log(`[AgentRunner:${this.config.hub}] ${msg}`)
  }

  /** Graceful shutdown — kill running tasks and disconnect */
  async stop(): Promise<void> {
    for (const [id, running] of this.runningTasks) {
      running.process.kill('SIGKILL')
      clearTimeout(running.timeout)
    }
    this.runningTasks.clear()
    this.ws?.close()
  }
}

// ── CLI ────────────────────────────────────────────────────────────────────────

function loadConfig(path: string): RunnerConfig {
  const raw = readFileSync(path, 'utf-8')
  return JSON.parse(raw)
}

if (require.main === module) {
  const args = argv.slice(2)
  let configPath = 'runner-config.json'
  let wsUrl = 'ws://localhost:8768'

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--config' && args[i + 1]) configPath = args[++i]
    if (args[i] === '--ws' && args[i + 1]) wsUrl = args[++i]
  }

  const config = loadConfig(configPath)
  config.wsUrl = config.wsUrl || wsUrl

  const runner = new AgentRunner(config)
  runner.start().then(() => {
    console.log(`Agent runner started with ${config.agents.length} agents`)
  }).catch((err) => {
    console.error('Failed to start:', err)
    process.exit(1)
  })

  process.on('SIGINT', () => {
    runner.stop().then(() => process.exit(0))
  })
}
