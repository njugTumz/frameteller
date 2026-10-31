import { mediaUrl } from '../../../shared/api/client'
import type { ServerEvent } from '../../../shared/events'
import { SessionSocket, closeMessage, sessionUrl, type SocketFactory } from '../../recording/session/sessionSocket'
import type { useRecordingStore } from '../../recording/store'
import type { useScriptStore } from '../store'
import { AudioQueue, type Player } from './audioQueue'

export interface ReaderDeps {
  recording: typeof useRecordingStore
  script: typeof useScriptStore
  socketFactory?: SocketFactory
  player?: Player
}

export interface ReadRequest {
  script: string
  format: 'text' | 'markdown' | 'fountain'
  voice: string
  language: string
}

/**
 * "Read it to me" for one project (ADR 0015): no microphone. The server voices each paragraph and the browser
 * plays them in order while their shots are directed and drawn. Pause holds the voice here and the reading on
 * the server; Continue goes on, also past an episode break before its drafts are done.
 */
export class Reader {
  private socket: SessionSocket | null = null
  private readonly queue: AudioQueue
  private readonly deps: ReaderDeps
  private readonly projectId: string
  private onEvent: (e: ServerEvent) => void = () => undefined

  constructor(projectId: string, deps: ReaderDeps) {
    this.projectId = projectId
    this.deps = deps
    this.queue = new AudioQueue((paragraph) => this.deps.script.getState().set({ current: paragraph ?? this.deps.script.getState().current }), deps.player)
  }

  use(onEvent: (e: ServerEvent) => void): void {
    this.onEvent = onEvent
  }

  async start(request: ReadRequest): Promise<void> {
    const rec = this.deps.recording.getState()
    if (rec.telling === 'connecting' || rec.telling === 'live') return
    rec.setProblem(null)
    rec.setTelling('connecting')
    this.socket?.close()
    const s = new SessionSocket(
      sessionUrl(this.projectId),
      { mode: 'read', keywords: [], keep_audio: false, script: request.script, script_format: request.format, voice: request.voice, language: request.language },
      {
        onEvent: (e) => this.handle(e),
        onClose: ({ code, expected }) => {
          if (this.socket !== s) return
          this.socket = null
          this.deps.recording.getState().setConnected(false)
          if (!expected) {
            this.queue.stop()
            this.deps.recording.getState().setProblem({ kind: 'connection', message: closeMessage(code) })
            this.deps.recording.getState().setTelling('idle')
          }
        },
      },
      this.deps.socketFactory,
    )
    this.socket = s
    try {
      await s.ready
      this.deps.recording.getState().setConnected(true)
    } catch (e) {
      this.deps.recording.getState().setProblem({ kind: 'connection', message: e instanceof Error ? e.message : closeMessage(0) })
      this.deps.recording.getState().setTelling('idle')
    }
  }

  private handle(e: ServerEvent): void {
    this.deps.recording.getState().apply(e) // the studio's dispatch fans it out to the other stores
    if (e.type === 'script.voiced') {
      const url = mediaUrl(e.audio_url)
      if (url) this.queue.add(e.paragraph, url)
    }
    this.onEvent(e)
  }

  pause(): void {
    if (this.socket?.send({ type: 'pause' })) {
      this.queue.pause()
      this.deps.script.getState().set({ reading: 'paused' })
    }
  }

  /** The screen locked while reading: hold the voice and the reading, as Pause does. */
  pauseForLock(): void {
    if (this.deps.script.getState().reading !== 'reading') return
    this.pause()
    this.deps.recording.getState().set({ pausedByLock: true })
  }

  /** Go on after a pause, or now rather than waiting for the episode's drafts. */
  resume(): void {
    this.deps.recording.getState().set({ pausedByLock: false })
    if (this.socket?.send({ type: 'continue' })) this.queue.resume()
  }

  stop(): void {
    this.queue.stop()
    if (this.socket?.end()) this.deps.recording.getState().setTelling('finishing')
  }

  dispose(): void {
    this.queue.stop()
    this.socket?.close()
    this.socket = null
  }
}
