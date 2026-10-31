import type { ButtonHTMLAttributes } from 'react'
import { cx } from './cx'

type Variant = 'ink' | 'outline' | 'marker' | 'quiet' | 'danger'
type Size = 'sm' | 'md' | 'lg'

const VARIANTS: Record<Variant, string> = {
  ink: 'border-ink bg-ink text-paper hover:border-blue-ink hover:bg-blue-ink',
  outline: 'border-ink bg-transparent text-ink hover:bg-ink hover:text-paper',
  // The one yellow marker accent: reserved for the action that moves the story on.
  marker: 'border-ink bg-marker text-marker-ink shadow-[3px_3px_0_var(--ink)] hover:shadow-[1px_1px_0_var(--ink)] hover:translate-x-[2px] hover:translate-y-[2px]',
  quiet: 'border-transparent bg-transparent text-ink underline decoration-blue decoration-2 underline-offset-4 hover:decoration-ink',
  danger: 'border-danger bg-transparent text-danger hover:bg-danger hover:text-paper',
}

const SIZES: Record<Size, string> = {
  sm: 'min-h-9 px-3 text-sm pointer-coarse:min-h-11 pointer-coarse:min-w-11',
  md: 'min-h-11 px-5',
  lg: 'min-h-14 px-7 text-lg',
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
}

export function Button({ variant = 'outline', size = 'md', className, type = 'button', ...rest }: ButtonProps) {
  return (
    <button
      type={type}
      className={cx(
        'inline-flex items-center justify-center gap-2 rounded-full border-2 font-semibold transition',
        'disabled:cursor-not-allowed disabled:opacity-45 disabled:shadow-none disabled:translate-0',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    />
  )
}
