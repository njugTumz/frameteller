import { useId, useState } from 'react'
import type { Animatic } from '../../../shared/api/types'
import { seconds } from '../../../shared/format'
import { Button } from '../../../shared/ui/Button'
import { Notice } from '../../../shared/ui/Notice'
import type { ExportJob } from '../../storyboard/store'

/** "Export animatic": progress while ffmpeg runs, then an inline player and a download. Plus the PDF sheet. */
export function ExportPanel({
  ready,
  job,
  animatic,
  videoSrc,
  downloadHref,
  pdfHref,
  voiceKept,
  error,
  onExport,
}: {
  /** Every shot has a panel. */
  ready: boolean
  job: ExportJob | null
  animatic: Animatic | null
  videoSrc: string | null
  downloadHref: string | null
  pdfHref: string
  voiceKept: boolean
  error: string | null
  onExport: (subtitles: boolean) => void
}) {
  const id = useId()
  const [subtitles, setSubtitles] = useState(false)
  const running = job?.status === 'queued' || job?.status === 'running'
  const percent = Math.round((job?.progress ?? 0) * 100)
  return (
    <section aria-labelledby={`${id}-title`} className="flex flex-col gap-3 rounded-md border-[1.5px] border-rule bg-sheet p-4" data-testid="export-panel">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id={`${id}-title`} className="m-0 text-sm font-bold uppercase tracking-wider text-muted">
          Animatic
        </h2>
        <a href={pdfHref} className="text-sm font-semibold underline" download>
          Download storyboard PDF
        </a>
      </div>
      <p className="m-0 text-sm text-muted">
        Each panel shows for as long as you spoke over it
        {voiceKept ? ', with your own voice.' : '. Your recording was not kept, so it will be silent.'}
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="ink" onClick={() => onExport(subtitles)} disabled={!ready || running}>
          {running ? 'Exporting…' : animatic ? 'Export again' : 'Export animatic'}
        </Button>
        <label htmlFor={`${id}-subs`} className="flex items-center gap-2 text-sm">
          <input id={`${id}-subs`} type="checkbox" checked={subtitles} onChange={(e) => setSubtitles(e.target.checked)} className="size-4 accent-[var(--ink)]" />
          Burn in subtitles
        </label>
      </div>
      {!ready && <p className="m-0 text-sm text-muted">Every shot needs a panel first.</p>}
      {running && (
        <div className="flex flex-col gap-1" role="status">
          <span className="text-sm font-semibold">{job.status === 'queued' ? 'Starting the export…' : `Rendering the animatic… ${percent}%`}</span>
          <progress max={100} value={percent} aria-label="Export progress" className="h-2 w-full accent-[var(--ink)]" />
        </div>
      )}
      {job?.status === 'failed' && <Notice tone="error" title={job.message ?? 'The animatic could not be exported. Try again.'} />}
      {error && <Notice tone="error" title={error} />}
      {animatic && videoSrc && !running && (
        <div className="flex flex-col gap-2">
          <video src={videoSrc} controls preload="metadata" className="frame w-full" data-testid="animatic-player" aria-label="The animatic" />
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted">
            <span>
              {seconds(animatic.duration_ms)}
              {animatic.subtitles ? ' · subtitles' : ''}
              {animatic.voiced ? ' · your voice' : ' · silent'}
            </span>
            {downloadHref && (
              <a href={downloadHref} className="font-semibold text-ink underline" download>
                Download MP4
              </a>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
