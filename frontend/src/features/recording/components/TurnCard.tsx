import { useId, useState, type FormEvent } from 'react'
import type { Turn } from '../../../shared/api/types'
import { MAX_CORRECTION_CHARS } from '../../../shared/events'
import { seconds } from '../../../shared/format'
import { Button } from '../../../shared/ui/Button'
import { replaceWord, words } from '../words'

type Editing = { kind: 'word'; index: number; value: string } | { kind: 'line'; value: string }

function BinIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />
    </svg>
  )
}

/**
 * One completed beat. Click a word to fix it; "Fix words" edits the whole line (and works from the keyboard).
 * Remove takes the beat out (with Undo); "⋯" merges it with the beat before or after it.
 */
export function TurnCard({
  turn,
  index,
  status,
  onCorrect,
  onRemove,
  onMerge,
  canMergePrevious = false,
  canMergeNext = false,
}: {
  turn: Turn
  index: number
  status: 'sending' | 'failed' | undefined
  onCorrect: (turnId: string, text: string) => void
  onRemove?: () => void
  onMerge?: (other: 'previous' | 'next') => void
  canMergePrevious?: boolean
  canMergeNext?: boolean
}) {
  const [editing, setEditing] = useState<Editing | null>(null)
  const [menu, setMenu] = useState(false)
  const menuId = useId()
  const fieldId = useId()
  const list = words(turn.text)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!editing) return
    const text = editing.kind === 'word' ? replaceWord(turn.text, editing.index, editing.value) : editing.value.trim()
    if (text && text !== turn.text) onCorrect(turn.id, text)
    setEditing(null)
  }

  return (
    <li className="arrive rounded-md border-[1.5px] border-rule bg-sheet p-3" data-testid="turn-card">
      <div className="mb-1 flex items-baseline justify-between text-xs text-muted tabular">
        <span className="font-semibold uppercase tracking-wide">Beat {index + 1}</span>
        <span>
          {seconds(turn.start_ms)} – {seconds(turn.end_ms)}
        </span>
      </div>
      {editing ? (
        <form onSubmit={submit} className="flex flex-col gap-2">
          <label htmlFor={fieldId} className="text-sm font-semibold">
            {editing.kind === 'word' ? `Fix “${list[editing.index] ?? ''}”` : 'Fix this line'}
          </label>
          {editing.kind === 'word' ? (
            <input
              id={fieldId}
              autoFocus
              value={editing.value}
              maxLength={80}
              onChange={(e) => setEditing({ ...editing, value: e.target.value })}
              onKeyDown={(e) => e.key === 'Escape' && setEditing(null)}
              className="rounded border-2 border-ink bg-paper px-2 py-1.5"
            />
          ) : (
            <textarea
              id={fieldId}
              autoFocus
              rows={3}
              value={editing.value}
              maxLength={MAX_CORRECTION_CHARS}
              onChange={(e) => setEditing({ ...editing, value: e.target.value })}
              onKeyDown={(e) => e.key === 'Escape' && setEditing(null)}
              className="rounded border-2 border-ink bg-paper px-2 py-1.5"
            />
          )}
          <div className="flex gap-2">
            <Button type="submit" variant="ink" size="sm">
              {editing.kind === 'word' ? 'Fix this word' : 'Fix this line'}
            </Button>
            <Button size="sm" onClick={() => setEditing(null)}>
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <>
          <p className="m-0 leading-relaxed">
            {list.map((w, i) => (
              <span key={i}>
                <button
                  type="button"
                  tabIndex={-1}
                  title="Click to fix this word"
                  onClick={() => setEditing({ kind: 'word', index: i, value: w })}
                  className="rounded-sm px-px hover:bg-wash hover:underline hover:decoration-blue hover:decoration-2"
                >
                  {w}
                </button>{' '}
              </span>
            ))}
          </p>
          <div className="mt-1 flex items-center justify-between gap-2">
            <span className="text-xs text-muted" role="status">
              {status === 'sending' ? 'Redirecting this shot…' : status === 'failed' ? 'That fix did not apply. Try again.' : ''}
            </span>
            <div className="relative flex items-center gap-1">
              <Button variant="quiet" size="sm" className="px-1" onClick={() => setEditing({ kind: 'line', value: turn.text })}>
                Fix words
              </Button>
              {onRemove && (
                <Button variant="quiet" size="sm" className="px-1" aria-label={`Remove beat ${index + 1}`} title="Remove this beat" onClick={onRemove}>
                  <BinIcon />
                </Button>
              )}
              {onMerge && (canMergePrevious || canMergeNext) && (
                <>
                  <Button
                    variant="quiet"
                    size="sm"
                    className="px-1.5"
                    aria-label={`More for beat ${index + 1}`}
                    aria-haspopup="menu"
                    aria-expanded={menu}
                    aria-controls={menuId}
                    onClick={() => setMenu((m) => !m)}
                    onKeyDown={(e) => e.key === 'Escape' && setMenu(false)}
                  >
                    ⋯
                  </Button>
                  {menu && (
                    <ul id={menuId} role="menu" className="absolute top-full right-0 z-10 m-0 mt-1 flex min-w-44 list-none flex-col rounded-md border-[1.5px] border-ink bg-paper p-1 shadow-md">
                      {canMergePrevious && (
                        <li role="none">
                          <button type="button" role="menuitem" className="w-full rounded px-2 py-1.5 text-left text-sm hover:bg-wash" onClick={() => (setMenu(false), onMerge('previous'))}>
                            Merge with previous
                          </button>
                        </li>
                      )}
                      {canMergeNext && (
                        <li role="none">
                          <button type="button" role="menuitem" className="w-full rounded px-2 py-1.5 text-left text-sm hover:bg-wash" onClick={() => (setMenu(false), onMerge('next'))}>
                            Merge with next
                          </button>
                        </li>
                      )}
                    </ul>
                  )}
                </>
              )}
            </div>
          </div>
        </>
      )}
    </li>
  )
}
