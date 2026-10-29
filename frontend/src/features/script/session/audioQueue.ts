/** The few members of HTMLAudioElement the queue uses, so tests can pass a fake. */
export type Player = Pick<HTMLAudioElement, 'src' | 'play' | 'pause' | 'onended' | 'onerror'>

/**
 * Plays synthesized paragraphs one after the other, in paragraph order, as they arrive. Pause holds the clip
 * playing now; resume carries on from where it stopped. A clip that fails to play is skipped.
 */
export class AudioQueue {
  private player: Player | null = null
  private readonly makePlayer: () => Player
  private readonly pending: { paragraph: number; url: string }[] = []
  private playing: number | null = null
  private paused = false
  private readonly onPlaying: (paragraph: number | null) => void

  constructor(onPlaying: (paragraph: number | null) => void, player?: Player) {
    this.makePlayer = () => player ?? new Audio() // created on the first clip, not before
    this.onPlaying = onPlaying
  }

  private get audio(): Player {
    if (!this.player) {
      this.player = this.makePlayer()
      this.player.onended = () => this.next()
      this.player.onerror = () => this.next()
    }
    return this.player
  }

  add(paragraph: number, url: string): void {
    if (this.pending.some((c) => c.paragraph === paragraph) || this.playing === paragraph) return
    this.pending.push({ paragraph, url })
    this.pending.sort((a, b) => a.paragraph - b.paragraph)
    if (this.playing === null && !this.paused) this.next()
  }

  get idle(): boolean {
    return this.playing === null && this.pending.length === 0
  }

  pause(): void {
    this.paused = true
    this.player?.pause()
  }

  resume(): void {
    this.paused = false
    if (this.playing !== null) void this.audio.play().catch(() => this.next())
    else this.next()
  }

  stop(): void {
    this.pending.length = 0
    this.player?.pause()
    this.playing = null
    this.onPlaying(null)
  }

  private next(): void {
    if (this.paused) {
      this.playing = null // the clip ended as the listener paused: the next one waits for resume
      return
    }
    const clip = this.pending.shift()
    this.playing = clip?.paragraph ?? null
    this.onPlaying(this.playing)
    if (!clip) return
    this.audio.src = clip.url
    void this.audio.play().catch(() => this.next())
  }
}
