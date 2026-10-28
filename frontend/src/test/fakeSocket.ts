import type { SocketLike } from '../features/recording/session/sessionSocket'
import type { ServerEvent } from '../shared/events'

/** A WebSocket stand-in: records what was sent and lets a test play the server. */
export class FakeSocket implements SocketLike {
  static all: FakeSocket[] = []
  readyState = 0
  bufferedAmount = 0
  binaryType: BinaryType = 'blob'
  sent: (string | ArrayBuffer)[] = []
  onopen: ((ev: Event) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  onclose: ((ev: CloseEvent) => void) | null = null
  onerror: ((ev: Event) => void) | null = null
  readonly url: string

  constructor(url: string) {
    this.url = url
    FakeSocket.all.push(this)
  }

  static factory = (url: string) => new FakeSocket(url)
  static latest(): FakeSocket {
    const s = FakeSocket.all.at(-1)
    if (!s) throw new Error('no socket was opened')
    return s
  }

  /** The JSON messages sent, parsed. */
  get json(): unknown[] {
    return this.sent.filter((m): m is string => typeof m === 'string').map((m) => JSON.parse(m) as unknown)
  }
  get binary(): ArrayBuffer[] {
    return this.sent.filter((m): m is ArrayBuffer => m instanceof ArrayBuffer)
  }

  open(): void {
    this.readyState = 1
    this.onopen?.(new Event('open'))
  }
  emit(event: ServerEvent): void {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(event) }))
  }
  /** Open and acknowledge the start message, like the server does. */
  start(): void {
    this.open()
    this.emit({ type: 'session.started', mode: 'narrate' })
  }
  send(data: string | ArrayBuffer): void {
    this.sent.push(data)
  }
  close(code = 1000): void {
    this.serverClose(code)
  }
  serverClose(code: number): void {
    if (this.readyState === 3) return
    this.readyState = 3
    this.onclose?.(new CloseEvent('close', { code }))
  }
}
