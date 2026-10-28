import { useState } from 'react'
import { Button } from '../../../shared/ui/Button'

/** A read-only link to the storyboard and animatic: create, copy, turn off. */
export function SharePanel({ link, busy, onShare, onRevoke }: { link: string | null; busy: boolean; onShare: () => void; onRevoke: () => void }) {
  const [copied, setCopied] = useState(false)
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
          <div>
            <Button size="sm" variant="quiet" onClick={onRevoke} disabled={busy}>
              Turn off the link
            </Button>
          </div>
        </>
      ) : (
        <>
          <p className="m-0 text-sm text-muted">A read-only page with your panels and animatic.</p>
          <div>
            <Button size="sm" onClick={onShare} disabled={busy}>
              {busy ? 'Making a link…' : 'Create a share link'}
            </Button>
          </div>
        </>
      )}
    </section>
  )
}
