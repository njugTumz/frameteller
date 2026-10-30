import { useId, useMemo } from 'react'
import { Button } from '../../../shared/ui/Button'
import { MAX_NAME, type Signature, byName, country as countryLabel } from '../../../shared/creator'

const field = 'rounded border-[1.5px] border-rule bg-paper px-2 py-1.5 text-sm'

/**
 * The optional signature on a gallery entry: a display name and a country. The suggested country is only
 * offered: it fills the field when the creator chooses "Use", and is never sent otherwise.
 */
export function CreatorFields({
  value,
  codes,
  suggested,
  onChange,
}: {
  value: Signature
  codes: string[]
  suggested: string | null
  onChange: (value: Signature) => void
}) {
  const id = useId()
  const options = useMemo(() => byName(codes), [codes])
  const offer = suggested && !value.country && codes.includes(suggested) ? suggested : null
  return (
    <fieldset className="m-0 flex flex-col gap-3 border-0 p-0" data-testid="creator-fields">
      <legend className="mb-1 text-sm font-semibold">Sign it (optional)</legend>
      <div className="flex flex-col gap-1">
        <label htmlFor={`${id}-name`} className="text-sm font-semibold">
          Your name
        </label>
        <input
          id={`${id}-name`}
          className={field}
          value={value.name}
          maxLength={MAX_NAME}
          autoComplete="nickname"
          aria-describedby={`${id}-name-hint`}
          onChange={(e) => onChange({ ...value, name: e.target.value })}
        />
        <p id={`${id}-name-hint`} className="m-0 text-xs text-muted">
          A display name or nickname, shown as the author. It doesn’t have to be your real name. {value.name.length}/{MAX_NAME}
        </p>
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor={`${id}-country`} className="text-sm font-semibold">
          Country
        </label>
        <select id={`${id}-country`} className={field} value={value.country} aria-describedby={offer ? `${id}-offer` : undefined} onChange={(e) => onChange({ ...value, country: e.target.value })}>
          <option value="">No country</option>
          {options.map((o) => (
            <option key={o.code} value={o.code}>
              {o.label}
            </option>
          ))}
        </select>
        {offer && (
          <p id={`${id}-offer`} className="m-0 flex flex-wrap items-center gap-2 text-xs text-muted" data-testid="country-suggestion">
            A guess from your browser: {countryLabel(offer)}. It’s only shown if you choose it.
            <Button size="sm" variant="outline" onClick={() => onChange({ ...value, country: offer })}>
              Use {countryLabel(offer)}
            </Button>
          </p>
        )}
      </div>
    </fieldset>
  )
}
