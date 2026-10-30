import { useRef, useState } from 'react'

/**
 * The animatic, never muted: a clear "Play with sound" button on top until it plays, then the browser's own
 * controls. Testers did not find the sound in a bare player, so the first click turns it on and up.
 */
export function AnimaticPlayer({ src, label, testId, voiced = true }: { src: string; label: string; testId: string; voiced?: boolean }) {
  const video = useRef<HTMLVideoElement>(null)
  const [started, setStarted] = useState(false)
  const play = () => {
    const v = video.current
    if (!v) return
    v.muted = false
    v.volume = 1
    setStarted(true)
    void v.play().catch(() => undefined) // the controls are there if the browser refuses
  }
  return (
    <div className="relative">
      <video ref={video} src={src} controls preload="metadata" playsInline className="frame w-full" data-testid={testId} aria-label={label} onPlay={() => setStarted(true)} />
      {!started && (
        <button
          type="button"
          onClick={play}
          className="absolute inset-0 m-auto flex h-fit w-fit items-center gap-2 rounded-full border-2 border-paper bg-ink px-5 py-3 font-bold text-paper shadow-lg hover:bg-blue-ink focus-visible:outline-4"
        >
          <span aria-hidden="true">▶</span>
          {voiced ? 'Play with sound' : 'Play (this animatic is silent)'}
        </button>
      )}
    </div>
  )
}
