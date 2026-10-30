import { useId, type FormEvent } from 'react'
import { Button } from '../../../shared/ui/Button'

export function EditBox({
  value,
  selectedLabel,
  dictation,
  sending,
  disabled,
  onChange,
  onSubmit,
  onMicDown,
  onMicUp,
}: {
  value: string
  selectedLabel: string | null
  dictation: 'idle' | 'recording' | 'transcribing'
  sending: boolean
  disabled: boolean
  onChange: (text: string) => void
  onSubmit: () => void
  onMicDown: () => void
  onMicUp: () => void
}) {
  const id = useId()
  const submit = (e: FormEvent) => {
    e.preventDefault()
    onSubmit()
  }
  const recording = dictation === 'recording'
  return (
    <form onSubmit={submit} className="flex flex-col gap-2" data-tour="edit-box">
      <label htmlFor={id} className="font-bold">
        Change how it looks
      </label>
      <p className="m-0 text-sm text-muted">
        {selectedLabel ? `Your change applies to ${selectedLabel}.` : 'Select an object first for a precise change, or describe the change for the whole panel.'}
      </p>
      <div className="flex items-start gap-2">
        <textarea
          id={id}
          rows={2}
          value={value}
          maxLength={500}
          placeholder="make her raincoat red"
          onChange={(e) => onChange(e.target.value)}
          className="min-w-0 flex-1 resize-y rounded border-2 border-ink bg-paper px-2 py-1.5"
        />
        <Button
          variant={recording ? 'ink' : 'outline'}
          aria-pressed={recording}
          aria-label={recording ? 'Stop and transcribe' : 'Say the change'}
          title="Press to talk, press again to stop"
          className="size-11 shrink-0 px-0"
          disabled={dictation === 'transcribing'}
          onClick={() => (recording ? onMicUp() : onMicDown())}
        >
          <svg viewBox="0 0 24 24" className="size-5" aria-hidden="true">
            <rect x="9" y="3" width="6" height="11" rx="3" fill={recording ? 'var(--marker)' : 'none'} stroke="currentColor" strokeWidth="2" />
            <path d="M5 11a7 7 0 0 0 14 0M12 18v3" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </Button>
      </div>
      <p className="m-0 min-h-5 text-sm text-muted" role="status">
        {recording ? 'Listening… press the mic again when you are done.' : dictation === 'transcribing' ? 'Writing down what you said…' : ''}
      </p>
      <Button type="submit" variant="ink" disabled={disabled || sending || !value.trim()}>
        {sending ? 'Sending…' : 'Make this change'}
      </Button>
    </form>
  )
}
