import { useId, useState } from 'react'
import { Button } from '../../../shared/ui/Button'

interface Props {
  link: string | null
  /** Search engines may list the share page. Off (the default): only people with the link find it. */
  isPublic: boolean
  busy: boolean
  /** Create the link, or switch an existing one between unlisted and public. */
  onShare: (isPublic: boolean) => void
  onRevoke: () => void
}

/** A read-only link to the storyboard and animatic: create, copy, make public, turn off. */
export function SharePanel({ link, isPublic, busy, onShare, onRevoke }: Props) {
  const id = useId()
  const [copied, setCopied] = useState(false)
  const [wantPublic, setWantPublic] = useState(false)
  const copy = async () => {
    if (!link) return
    try {
      await navigator.clipboard.writeText(link)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }
  const checked = link ? isPublic : wantPublic
  const publicToggle = (
    <div className="flex flex-col gap-0.5">
      <label htmlFor={`${id}-public`} className="flex items-center gap-2 text-sm font-semibold">
        <input
          id={`${id}-public`}
          type="checkbox"
          checked={checked}
          disabled={busy}
          aria-describedby={`${id}-public-help`}
          onChange={(e) => (link ? onShare(e.target.checked) : setWantPublic(e.target.checked))}
        />
        Make public
      </label>
      <p id={`${id}-public-help`} className="m-0 text-xs text-muted">
        {checked ? 'Search engines may list this page.' : 'Unlisted: search engines leave it out; only people with the link can open it.'}
      </p>
    </div>
  )
  return (
    <section aria-label="Share" className="flex flex-col gap-2 rounded-md border-[1.5px] border-rule bg-sheet p-4" data-testid="share-panel">
      <h2 className="m-0 text-sm font-bold uppercase tracking-wider text-muted">Share</h2>
      {link ? (
        <>
          <p className="m-0 text-sm text-muted">Anyone with this link can watch, not edit. It previews on X.</p>
          <div className="flex gap-2">
            <input readOnly value={link} aria-label="Share link" onFocus={(e) => e.target.select()} className="min-w-0 flex-1 rounded border-[1.5px] border-rule bg-paper px-2 py-1.5 text-sm" />
            <Button size="sm" variant="ink" onClick={() => void copy()}>
              {copied ? 'Copied' : 'Copy'}
            </Button>
          </div>
          {publicToggle}
          <div>
            <Button size="sm" variant="quiet" onClick={onRevoke} disabled={busy}>
              Turn off the link
            </Button>
          </div>
        </>
      ) : (
        <>
          <p className="m-0 text-sm text-muted">A read-only page with your panels and animatic.</p>
          {publicToggle}
          <div>
            <Button size="sm" onClick={() => onShare(wantPublic)} disabled={busy}>
              {busy ? 'Making a link…' : 'Create a share link'}
            </Button>
          </div>
        </>
      )}
    </section>
  )
}
