import { cx } from '../shared/ui/cx'
import { THEMES, type ThemeChoice } from './theme'

const LABELS: Record<ThemeChoice, string> = { system: 'Auto', light: 'Light', dark: 'Dark' }

/** Auto / Light / Dark. `menu`: the phone header menu's larger segments (44 px taps), beside a visible label. */
export function ThemeSwitch({ value, onChange, place = 'bar' }: { value: ThemeChoice; onChange: (next: ThemeChoice) => void; place?: 'bar' | 'menu' }) {
  const menu = place === 'menu'
  return (
    <fieldset className={cx('flex rounded-full border-2 border-rule p-0.5', menu ? 'm-0 text-base' : 'text-sm')}>
      <legend className="sr-only">Theme</legend>
      {THEMES.map((t) => (
        <label
          key={t}
          className={cx(
            'cursor-pointer rounded-full text-muted has-checked:bg-ink has-checked:text-paper has-focus-visible:outline-3 has-focus-visible:outline-focus',
            menu ? 'flex min-h-11 min-w-16 items-center justify-center px-3' : 'px-2.5 py-1',
          )}
        >
          <input type="radio" name={menu ? 'theme-menu' : 'theme'} value={t} checked={value === t} onChange={() => onChange(t)} className="sr-only" />
          {LABELS[t]}
        </label>
      ))}
    </fieldset>
  )
}
