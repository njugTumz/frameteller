import { MAX_KEYWORDS, type ScriptFormat, type ServerEvent, type StartMessage } from '../../../shared/events'
import { micError, openMicrophone, type MicError, type Microphone } from '../../../shared/audio/microphone'
import type { ProblemKind, RecordingState, Telling, useRecordingStore } from '../store'
import { SessionSocket, closeMessage, sessionUrl, type SocketFactory } from './sessionSocket'

const RECONNECT_DELAYS_MS = [500, 1500, 4000]
/**
 * Audio captured while the socket connects (or reconnects) is held and sent once the session starts, so the
 * first words are not lost. At most 2 s: the backend already sends its own handshake backlog to the
 * transcriber in one go, and the transcriber rejects streams that run far ahead of real time.
 */
export const MAX_BACKLOG_FRAMES = 25
const FINAL_CODES = [4400, 4404, 4409]

const MIC_PROBLEMS: Record<MicError['problem'], ProblemKind> = {
  blocked: 'mic-blocked',
  missing: 'mic-missing',
  busy: 'mic-busy',
  unsupported: 'mic-unsupported',
  lost: 'mic-lost',
}

export const RECONNECTED =
  'The connection dropped, so a new session started. Keep telling: new shots continue the storyboard.'

export interface NarrationDeps {
  store: typeof useRecordingStore
  openMic?: typeof openMicrophone
  socketFactory?: SocketFactory
  wait?: (ms: number) => Promise<void>
}

export interface NarrationHandlers {
  onEvent(e: ServerEvent): void
  /** Names to bias recognition with, beyond the ones the narrator typed (e.g. the cast). */
  extraKeywords: readonly string[]
  /** Teleprompter (ADR 0015): the script read aloud; each paragraph is cut when the reader reaches its end. */
  script?: { text: string; format: ScriptFormat } | null
  /** The language the narrator speaks (a locale), passed to the transcriber; '' or missing: auto-detect. */
  language?: string
}

/**
 * One project's narration: microphone → 80 ms PCM frames → session WebSocket, and server events → the store
 * and onEvent. A dropped socket reconnects with a new session (the backend has no resume) and says so.
 * After session.ended the socket stays open, so job updates keep arriving.
 */
export class Narration {
  private mic: Microphone | null = null
  private socket: SocketSession | null = null
  private streaming = false
  private backlog: ArrayBuffer[] = []
  private disposed = false
  private readonly deps: NarrationDeps
  private readonly projectId: string
  private handlers: NarrationHandlers = { onEvent: () => undefined, extraKeywords: [] }

  constructor(projectId: string, deps: NarrationDeps) {
    this.projectId = projectId
    this.deps = deps
  }

  /** The latest event handler and keywords, from the component that owns this narration. */
  use(handlers: NarrationHandlers): void {
    this.handlers = handlers
  }

  /** Mounted (again, under StrictMode): accept work. */
  attach(): void {
    this.disposed = false
  }

  private get state(): RecordingState & ReturnType<typeof useRecordingStore.getState> {
    return this.deps.store.getState()
  }

  /** Read afresh: it changes while awaiting the microphone or the socket. */
  private telling(): Telling {
    return this.deps.store.getState().telling
  }

  private keywords(): string[] {
    const all = [...this.state.keywords, ...this.handlers.extraKeywords].map((k) => k.trim()).filter(Boolean)
    return [...new Set(all)].slice(0, MAX_KEYWORDS)
  }

  private async connect(onDrop: (code: number) => void): Promise<SocketSession> {
    const script = this.handlers.script
    const language = this.handlers.language ? { language: this.handlers.language } : {}
    const start: StartMessage = script
      ? { mode: 'teleprompter', keywords: this.keywords(), keep_audio: this.state.keepAudio, script: script.text, script_format: script.format, ...language }
      : { mode: 'narrate', keywords: this.keywords(), keep_audio: this.state.keepAudio, ...language }
    const s: SocketSession = new SessionSocket(
      sessionUrl(this.projectId),
      start,
      {
        onEvent: (e) => {
          this.state.apply(e)
          this.handlers.onEvent(e)
        },
        onClose: ({ code, expected }) => {
          if (this.socket !== s) return
          this.socket = null
          this.streaming = false
          this.state.setConnected(false)
          if (!expected && !this.disposed) {
            this.state.set({ updating: true }) // cleared once the project has been fetched again
            onDrop(code)
          }
        },
      },
      this.deps.socketFactory,
    )
    this.socket = s
    await s.ready
    this.state.setConnected(true)
    for (const frame of this.backlog.splice(0)) s.sendAudio(frame)
    this.streaming = true
    return s
  }

  private frame(pcm: ArrayBuffer): void {
    if (this.streaming && this.socket?.sendAudio(pcm)) return
    this.backlog.push(pcm)
    if (this.backlog.length > MAX_BACKLOG_FRAMES) this.backlog.shift()
  }

  private stopMic(): void {
    void this.mic?.close()
    this.mic = null
    this.backlog = []
    this.state.setLevel(0)
  }

  private fail(kind: ProblemKind, message: string): void {
    this.stopMic()
    this.socket?.close()
    this.socket = null
    this.state.setProblem({ kind, message })
    this.state.setTelling('idle')
  }

  /** The socket dropped mid-narration: start a new session and keep going. */
  private async reconnect(code: number, attempt = 0): Promise<void> {
    const { telling } = this.state
    if (this.disposed || (telling !== 'live' && telling !== 'finishing' && telling !== 'connecting')) return
    if (FINAL_CODES.includes(code) || attempt >= RECONNECT_DELAYS_MS.length) {
      this.fail('connection', closeMessage(code))
      return
    }
    this.state.setTelling('connecting')
    await (this.deps.wait ?? ((ms) => new Promise((r) => setTimeout(r, ms))))(RECONNECT_DELAYS_MS[attempt] ?? 0)
    try {
      const s = await this.connect((next) => void this.reconnect(next))
      if (this.mic) {
        this.state.setTelling('live')
        this.state.notice(RECONNECTED)
      } else {
        s.end() // it dropped while finishing: the new session has nothing to transcribe
        this.state.setTelling('finishing')
      }
    } catch {
      await this.reconnect(code, attempt + 1)
    }
  }

  private openMic(): Promise<Microphone> {
    return (this.deps.openMic ?? openMicrophone)(
      {
        onFrame: (pcm) => this.frame(pcm),
        onLevel: (level) => this.state.setLevel(level),
        onLost: (error) => this.micLost(error),
        onSwitched: (label) => {
          this.state.set({ micLabel: label })
          this.state.notice(`Now recording from ${label}.`)
        },
      },
      undefined,
      { deviceId: this.state.deviceId ?? undefined },
    )
  }

  async start(): Promise<void> {
    const { telling } = this.state
    if (this.disposed || telling === 'mic' || telling === 'connecting' || telling === 'live') return
    this.state.setProblem(null)
    this.state.set({ silent: false, heardNothing: false, pausedByLock: false })
    this.state.setTelling('mic')
    try {
      this.mic = await this.openMic()
      this.state.set({ micLabel: this.mic.label })
    } catch (e) {
      const error = micError(e)
      this.fail(MIC_PROBLEMS[error.problem], error.message)
      return
    }
    if (this.disposed || this.telling() !== 'mic') return this.stopMic() // left, or the screen locked meanwhile
    this.state.setTelling('connecting')
    try {
      this.socket?.close() // one kept open after a previous session.ended
      this.streaming = false
      await this.connect((code) => void this.reconnect(code))
      this.state.setTelling('live')
    } catch (e) {
      if (this.state.telling === 'idle') return // left the line
      this.fail('connection', e instanceof Error ? e.message : closeMessage(0))
    }
  }

  private micLost(error: MicError): void {
    this.stopMic()
    const ended = this.socket?.end() ?? false // keep what was said: finish the session normally
    // iOS ends the microphone when the screen locks: that is a pause, not a broken microphone.
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') this.state.set({ pausedByLock: true })
    else this.state.setProblem({ kind: MIC_PROBLEMS[error.problem], message: error.message })
    this.state.setTelling(ended ? 'finishing' : 'idle')
  }

  /**
   * The screen locked or the page was hidden mid-narration: stop the microphone and end the session normally,
   * so every completed beat (and the one being spoken) becomes a shot. Start telling goes on afterwards.
   */
  pauseForLock(): void {
    const { telling } = this.state
    if (telling !== 'live' && telling !== 'connecting' && telling !== 'mic') return
    if (telling === 'mic') {
      // Still asking for the microphone: drop it once it arrives.
      this.state.setTelling('idle')
    } else this.stop()
    this.state.set({ pausedByLock: true })
  }

  /**
   * "We can't hear you": record from another microphone. While live, the session carries on with the new
   * device (frames keep flowing to the same socket); otherwise it is used the next time telling starts.
   */
  async useMicrophone(deviceId: string): Promise<void> {
    this.state.set({ deviceId, silent: false })
    if (!this.mic || this.state.telling !== 'live') return
    const previous = this.mic
    try {
      this.mic = await this.openMic()
    } catch (e) {
      this.mic = previous
      this.state.notice(micError(e).message)
      return
    }
    void previous.close()
    this.state.set({ micLabel: this.mic.label })
  }

  stop(): void {
    const { telling } = this.state
    if (telling !== 'live' && telling !== 'connecting') return
    this.stopMic()
    if (telling === 'connecting') {
      // Still connecting, or waiting in line in a busy studio (ADR 0016): leave without a session.
      this.socket?.close()
      this.socket = null
      this.state.set({ queue: null })
      this.state.setTelling('idle')
      return
    }
    this.state.setTelling(this.socket?.end() ? 'finishing' : 'idle')
  }

  beat(): boolean {
    if (this.state.telling !== 'live' || !this.socket?.beat()) return false
    this.state.beatSent()
    return true
  }

  correct(turnId: string, text: string): void {
    const send = (s: SocketSession) => {
      if (s.correct(turnId, text)) this.state.correctionSent(turnId)
    }
    if (this.socket?.isOpen) return send(this.socket)
    // The socket timed out after the session: open one just for this correction, then end it.
    this.connect(() => undefined)
      .then((s) => {
        send(s)
        s.end()
      })
      .catch(() => this.state.notice('The studio is not answering, so the correction was not sent. Try again.'))
  }

  dispose(): void {
    this.disposed = true
    this.stopMic()
    this.socket?.close()
    this.socket = null
    this.state.setConnected(false)
  }
}

type SocketSession = SessionSocket
