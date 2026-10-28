import type { ReactNode } from 'react'
import { Button } from '../../../shared/ui/Button'
import { Notice } from '../../../shared/ui/Notice'
import type { ApprovalBlock } from '../store'

const BLOCKED: Record<Exclude<ApprovalBlock, null>, string> = {
  'no-cast': 'Characters you mention get a reference sheet here.',
  drawing: 'Reference sheets are still being drawn. You can approve once they are all here.',
  'missing-sheet': 'A sheet is missing. Regenerate it, then approve.',
}

export function CastTray({
  status,
  block,
  approving,
  pending,
  error,
  children,
  onApprove,
  onChange,
}: {
  status: 'draft' | 'approved'
  block: ApprovalBlock
  approving: boolean
  pending: string[]
  error: string | null
  children: ReactNode
  onApprove: () => void
  onChange: () => void
}) {
  const approved = status === 'approved'
  return (
    <section aria-labelledby="cast-title" className="flex flex-col gap-3 rounded-md border-[1.5px] border-rule bg-paper/80 p-4" data-testid="cast-tray" data-status={status}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="cast-title" className="m-0 text-sm font-bold uppercase tracking-wider text-muted">
            Cast {approved && <span className="ml-1 rounded-full bg-wash px-2 py-0.5 text-xs text-ink normal-case">approved</span>}
          </h2>
          <p className="m-0 mt-1 text-sm text-muted" role="status">
            {approved
              ? 'Every panel uses these sheets, so the characters look the same in each frame.'
              : block === 'no-cast'
                ? BLOCKED['no-cast']
                : 'Check each character. Panels are drawn from these sheets, and any mistake here shows up in every panel. Fix a description or regenerate a sheet, then approve.'}
          </p>
        </div>
        {approved ? (
          <Button size="sm" onClick={onChange}>
            Change the cast
          </Button>
        ) : (
          block !== 'no-cast' && (
            <Button variant="ink" onClick={onApprove} disabled={block !== null || approving}>
              {approving ? 'Approving…' : 'Approve cast'}
            </Button>
          )
        )}
      </div>
      {!approved && block && block !== 'no-cast' && <p className="m-0 text-sm font-semibold">{BLOCKED[block]}</p>}
      {pending.length > 0 && (
        <p className="m-0 text-sm text-muted" aria-live="polite">
          Drawing sheets for {pending.join(', ')}…
        </p>
      )}
      {error && <Notice tone="error" title={error} />}
      <ul className="m-0 flex list-none gap-3 overflow-x-auto p-0 pb-1">{children}</ul>
    </section>
  )
}
