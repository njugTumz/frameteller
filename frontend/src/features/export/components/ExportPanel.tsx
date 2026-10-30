import { useId, useState } from 'react'
import type { Animatic } from '../../../shared/api/types'
import { seconds } from '../../../shared/format'
import { Button } from '../../../shared/ui/Button'
import { AnimaticPlayer } from '../../../shared/ui/AnimaticPlayer'
import { Notice } from '../../../shared/ui/Notice'
import type { ExportJob } from '../../storyboard/store'
import { type AnimaticChoice, CAPTION_LANGUAGES } from '../captions'

/** "Export animatic": progress while ffmpeg runs, then an inline player and a download. Plus the PDF sheet. */
export function ExportPanel({
  ready,
  job,
  animatic,
  videoSrc,
  downloadHref,
  captionsHref = null,
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
  /** The captions as an .srt file. */
  captionsHref?: string | null
  pdfHref: string
  voiceKept: boolean
  error: string | null
  onExport: (choice: AnimaticChoice) => void
}) {
  const id = useId()
  const [subtitles, setSubtitles] = useState(true)
  const [captionLanguage, setCaptionLanguage] = useState('')
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
        <Button variant="ink" onClick={() => onExport({ subtitles, captionLanguage: captionLanguage || null })} disabled={!ready || running}>
          {running ? 'Exporting…' : animatic ? 'Export again' : 'Export animatic'}
        </Button>
        <label htmlFor={`${id}-subs`} className="flex items-center gap-2 text-sm">
          <input id={`${id}-subs`} type="checkbox" checked={subtitles} onChange={(e) => setSubtitles(e.target.checked)} className="size-4 accent-[var(--ink)]" />
          Captions in the picture
        </label>
        <label htmlFor={`${id}-lang`} className="flex items-center gap-2 text-sm">
          Captions in
          <select
            id={`${id}-lang`}
            value={captionLanguage}
            onChange={(e) => setCaptionLanguage(e.target.value)}
            className="rounded-sm border-[1.5px] border-rule bg-paper px-2 py-1"
          >
            <option value="">the language spoken</option>
            {CAPTION_LANGUAGES.map((l) => (
              <option key={l.locale} value={l.locale}>
                {l.name}
              </option>
            ))}
          </select>
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
          <AnimaticPlayer key={videoSrc} src={videoSrc} label="The animatic" testId="animatic-player" voiced={animatic.voiced} />
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted">
            <span>
              {seconds(animatic.duration_ms)}
              {animatic.subtitles ? ' · captions' : ''}
              {animatic.caption_language ? ` · ${CAPTION_LANGUAGES.find((l) => l.locale === animatic.caption_language)?.name ?? animatic.caption_language}` : ''}
              {animatic.voiced ? ' · your voice' : ' · silent'}
            </span>
            <span className="flex flex-wrap gap-3">
              {captionsHref && (
                <a href={captionsHref} className="font-semibold text-ink underline" download>
                  Captions (.srt)
                </a>
              )}
              {downloadHref && (
                <a href={downloadHref} className="font-semibold text-ink underline" download>
                  Download MP4
                </a>
              )}
            </span>
          </div>
        </div>
      )}
    </section>
  )
}
