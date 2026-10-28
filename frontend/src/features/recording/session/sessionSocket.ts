import { wsBaseUrl } from '../../../config'
import { CLOSE, parseServerEvent, type ClientMessage, type ServerEvent, type StartMessage } from '../../../shared/events'

export function sessionUrl(projectId: string, base = wsBaseUrl()): string {
  return `${base}/ws/projects/${encodeURIComponent(projectId)}/session`
}

export interface SocketClosed {
  code: number
  /** We closed it, or the server ended it normally after the session. */
  expected: boolean
}

export interface SocketLike {
  readyState: number
  bufferedAmount: number
  binaryType: BinaryType
  send(data: string | ArrayBuffer): void
  close(code?: number): void
  onopen: ((ev: Event) => void) | null
  onmessage: ((ev: MessageEvent) => void) | null
  onclose: ((ev: CloseEvent) => void) | null
  onerror: ((ev: Event) => void) | null
}

export type SocketFactory = (url: string) => SocketLike

export interface SocketHandlers {
  onEvent(e: ServerEvent): void
  onClose(info: SocketClosed): void
}

/** Past this much unsent audio the network is not keeping up; drop frames rather than fall further behind. */
const MAX_BUFFERED_BYTES = 256 * 1024
const OPEN = 1

/** User-facing reasons for the close codes in docs/api-events.md. */
export function closeMessage(code: number): string {
  switch (code) {
    case CLOSE.busy:
      return 'This story is being told in another tab or window. Finish there, or close that tab, then start again.'
    case CLOSE.notFound:
      return 'This storyboard no longer exists. Start a new story.'
    case CLOSE.policy:
      return 'The studio refused the connection from this address, or too many were opened at once. Wait a minute and try again.'
    case CLOSE.badStart:
      return 'The studio did not understand how the session started. Reload the page and try again.'
    default:
      return 'The connection to the studio dropped.'
  }
}

/**
 * One live session on /ws/projects/{id}/session. Resolves `ready` on session.started; every parsed event goes
 * to onEvent. After session.ended the socket stays open for job updates until close().
 */
export class SessionSocket {
  private readonly socket: SocketLike
  private readonly handlers: SocketHandlers
  private closing = false
  private ended = false
  readonly ready: Promise<void>

  constructor(url: string, start: StartMessage, handlers: SocketHandlers, factory: SocketFactory = (u) => new WebSocket(u)) {
    this.handlers = handlers
    this.socket = factory(url)
    this.socket.binaryType = 'arraybuffer'
    this.ready = new Promise((resolve, reject) => {
      let started = false
      this.socket.onopen = () => this.socket.send(JSON.stringify(start))
      this.socket.onmessage = (m) => {
        const event = parseServerEvent(m.data)
        if (!event) return
        if (event.type === 'session.started') {
          started = true
          resolve()
        }
        if (event.type === 'session.ended') this.ended = true
        this.handlers.onEvent(event)
      }
      this.socket.onerror = () => undefined // onclose follows with the code
      this.socket.onclose = (e) => {
        if (!started) reject(new Error(closeMessage(e.code)))
        this.handlers.onClose({ code: e.code, expected: this.closing || (this.ended && e.code === CLOSE.normal) })
      }
    })
    this.ready.catch(() => undefined) // callers that never await it must not see an unhandled rejection
  }

  get isOpen(): boolean {
    return this.socket.readyState === OPEN
  }

  /** Send one PCM frame. Returns false when it was dropped (socket closed, or the network is behind). */
  sendAudio(pcm: ArrayBuffer): boolean {
    if (!this.isOpen || this.socket.bufferedAmount > MAX_BUFFERED_BYTES) return false
    this.socket.send(pcm)
    return true
  }

  send(message: ClientMessage): boolean {
    if (!this.isOpen) return false
    this.socket.send(JSON.stringify(message))
    return true
  }

  beat(): boolean {
    return this.send({ type: 'beat' })
  }

  correct(turnId: string, text: string): boolean {
    return this.send({ type: 'transcript.corrected', turn_id: turnId, text })
  }

  /** The narration is done; the server finishes transcribing and directing, then sends session.ended. */
  end(): boolean {
    return this.send({ type: 'end' })
  }

  close(): void {
    this.closing = true
    if (this.socket.readyState <= OPEN) this.socket.close(CLOSE.normal)
  }
}
