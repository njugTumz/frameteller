import type { ReactNode } from 'react'
import { APP_NAME } from '../config'
import { BrandMark } from '../shared/ui/BrandMark'

export function TopBar({ title, children }: { title?: string; children?: ReactNode }) {
  return (
    <header className="flex items-center justify-between gap-4 border-b-[1.5px] border-rule bg-paper/85 px-4 py-3 backdrop-blur md:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <a href="/" className="flex shrink-0 items-center gap-2 text-lg font-extrabold tracking-tight no-underline wide">
          <BrandMark />
          <span>{APP_NAME}</span>
        </a>
        {title && (
          <>
            <span aria-hidden="true" className="text-rule">/</span>
            <h1 className="m-0 truncate text-base font-semibold">{title}</h1>
          </>
        )}
      </div>
      <div className="flex items-center gap-3">{children}</div>
    </header>
  )
}
