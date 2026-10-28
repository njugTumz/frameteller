import { THEMES, type ThemeChoice } from './theme'

const LABELS: Record<ThemeChoice, string> = { system: 'Auto', light: 'Light', dark: 'Dark' }

export function ThemeSwitch({ value, onChange }: { value: ThemeChoice; onChange: (next: ThemeChoice) => void }) {
  return (
    <fieldset className="flex rounded-full border-2 border-rule p-0.5 text-sm">
      <legend className="sr-only">Theme</legend>
      {THEMES.map((t) => (
        <label
          key={t}
          className="cursor-pointer rounded-full px-2.5 py-1 text-muted has-checked:bg-ink has-checked:text-paper has-focus-visible:outline-3 has-focus-visible:outline-focus"
        >
          <input type="radio" name="theme" value={t} checked={value === t} onChange={() => onChange(t)} className="sr-only" />
          {LABELS[t]}
        </label>
      ))}
    </fieldset>
  )
}
