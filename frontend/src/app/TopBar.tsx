import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { APP_NAME } from '../config'
import { BrandMark } from '../shared/ui/BrandMark'
import { Button } from '../shared/ui/Button'
import { usePathname } from './router'

/** One header action: a link, or a button (Take the tour, Report a problem). */
export type HeaderAction = { label: string; href: string } | { label: string; onSelect: () => void }

/**
 * The app's header. From 720 px: the logo, the actions and the theme switch in one row, as always.
 * Below: the logo, the judge badge and a ☰ button whose menu holds the actions and the theme switch.
 */
export function TopBar({
  title,
  badge,
  actions = [],
  menuOnly = [],
  theme,
}: {
  title?: string
  /** Stays in the bar at every width (the judge badge). */
  badge?: ReactNode
  /** In the bar from 720 px, and in the menu below. */
  actions?: HeaderAction[]
  /** Only in the phone menu (Privacy: on wide screens it is in the page). */
  menuOnly?: HeaderAction[]
  /** The theme switch, rendered once per place it shows (the bar, the menu). */
  theme?: (place: 'bar' | 'menu') => ReactNode
}) {
  return (
    <header className="relative z-30 flex items-center justify-between gap-3 border-b-[1.5px] border-rule bg-paper/85 px-4 py-2 backdrop-blur min-[720px]:gap-4 min-[720px]:py-3 md:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <a href="/" className="flex min-w-0 shrink items-center gap-2 text-lg pointer-coarse:min-h-11 font-extrabold tracking-tight no-underline wide">
          <BrandMark />
          <span className="truncate">{APP_NAME}</span>
        </a>
        {title && (
          <>
            <span aria-hidden="true" className="text-rule">
              /
            </span>
            <h1 className="m-0 truncate text-base font-semibold">{title}</h1>
          </>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-2 min-[720px]:gap-3">
        {badge}
        <div className="hidden items-center gap-3 min-[720px]:flex" data-testid="header-actions">
          {actions.map((a) => (
            <ActionItem key={a.label} action={a} place="bar" />
          ))}
          {theme?.('bar')}
        </div>
        {(actions.length > 0 || menuOnly.length > 0 || theme) && <HeaderMenu actions={[...actions, ...menuOnly]} theme={theme} />}
      </div>
    </header>
  )
}

function ActionItem({ action, place, onDone }: { action: HeaderAction; place: 'bar' | 'menu'; onDone?: () => void }) {
  if (place === 'bar')
    return 'href' in action ? (
      <a href={action.href} className="text-sm font-semibold underline-offset-2 hover:underline pointer-coarse:inline-flex pointer-coarse:min-h-11 pointer-coarse:items-center">
        {action.label}
      </a>
    ) : (
      <Button size="sm" variant="quiet" onClick={action.onSelect}>
        {action.label}
      </Button>
    )
  const look = 'flex min-h-12 w-full items-center rounded-md px-3 text-left text-base font-semibold no-underline hover:bg-wash focus-visible:bg-wash'
  if ('href' in action)
    return (
      <a href={action.href} className={look} onClick={onDone}>
        {action.label}
      </a>
    )
  return (
    <button
      type="button"
      className={look}
      onClick={() => {
        onDone?.()
        action.onSelect()
      }}
    >
      {action.label}
    </button>
  )
}

/** The ☰ menu below 720 px. Esc, an outside tap or a navigation closes it; focus goes in, and back to ☰. */
function HeaderMenu({ actions, theme }: { actions: HeaderAction[]; theme?: (place: 'bar' | 'menu') => ReactNode }) {
  const id = useId()
  const pathname = usePathname()
  // Open on the page it was opened on: any navigation closes it.
  const [openOn, setOpenOn] = useState<string | null>(null)
  const open = openOn === pathname
  const setOpen = (next: boolean) => setOpenOn(next ? pathname : null)
  const button = useRef<HTMLButtonElement>(null)
  const panel = useRef<HTMLDivElement>(null)
  const close = (refocus: boolean) => {
    setOpen(false)
    if (refocus) button.current?.focus()
  }

  useEffect(() => {
    if (!open) return
    panel.current?.querySelector<HTMLElement>('a, button, input')?.focus()
    const outside = (e: PointerEvent) => {
      const t = e.target as Node
      if (!panel.current?.contains(t) && !button.current?.contains(t)) setOpenOn(null)
    }
    const key = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.stopPropagation()
      setOpenOn(null)
      button.current?.focus()
    }
    // A wider window (a phone turned sideways, a resized desktop) shows the actions in the bar.
    const wide = typeof window.matchMedia === 'function' ? window.matchMedia('(min-width: 720px)') : null
    const resized = () => wide?.matches && setOpenOn(null)
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', key, true)
    wide?.addEventListener('change', resized)
    return () => {
      document.removeEventListener('pointerdown', outside)
      document.removeEventListener('keydown', key, true)
      wide?.removeEventListener('change', resized)
    }
  }, [open])

  return (
    <div className="min-[720px]:hidden">
      <button
        ref={button}
        type="button"
        className="inline-flex size-11 items-center justify-center rounded-full border-2 border-ink bg-paper text-ink"
        aria-label="Menu"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
      >
        <svg viewBox="0 0 20 20" aria-hidden="true" className="size-5" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round">
          {open ? <path d="M5 5l10 10M15 5L5 15" /> : <path d="M3 5.5h14M3 10h14M3 14.5h14" />}
        </svg>
      </button>
      <div
        ref={panel}
        id={id}
        hidden={!open}
        data-testid="header-menu"
        className="absolute inset-x-0 top-full z-40 border-b-[1.5px] border-rule bg-paper px-4 pt-2 pb-4 shadow-md"
        onBlur={(e) => {
          const next = e.relatedTarget as Node | null
          if (next && !panel.current?.contains(next) && !button.current?.contains(next)) setOpen(false)
        }}
      >
        <nav aria-label="Menu">
          <ul className="m-0 flex list-none flex-col gap-1 p-0">
            {actions.map((a) => (
              <li key={a.label}>
                <ActionItem action={a} place="menu" onDone={() => close(false)} />
              </li>
            ))}
          </ul>
        </nav>
        {theme && (
          <div className="mt-3 flex items-center justify-between gap-3 border-t-[1.5px] border-rule px-3 pt-3">
            <span aria-hidden="true" className="font-semibold">
              Theme
            </span>
            {theme('menu')}
          </div>
        )}
      </div>
    </div>
  )
}
