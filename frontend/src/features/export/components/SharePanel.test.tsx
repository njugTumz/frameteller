import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { SharePanel } from './SharePanel'

const props = (over: Partial<Parameters<typeof SharePanel>[0]> = {}) => ({ link: null, isPublic: false, busy: false, onShare: vi.fn(), onRevoke: vi.fn(), ...over })

describe('SharePanel', () => {
  it('creates an unlisted link unless Make public is ticked first', async () => {
    const p = props()
    const { rerender } = render(<SharePanel {...p} />)
    expect((screen.getByLabelText('Make public') as HTMLInputElement).checked).toBe(false)
    expect(screen.getByText(/Unlisted: search engines leave it out/)).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: 'Create a share link' }))
    expect(p.onShare).toHaveBeenLastCalledWith(false)

    rerender(<SharePanel {...p} />)
    await userEvent.click(screen.getByLabelText('Make public'))
    expect(p.onShare).toHaveBeenCalledTimes(1) // ticking alone does not create a link
    await userEvent.click(screen.getByRole('button', { name: 'Create a share link' }))
    expect(p.onShare).toHaveBeenLastCalledWith(true)
  })

  it('switches an existing link between unlisted and public', async () => {
    const p = props({ link: 'https://api.example/s/tok' })
    const { rerender } = render(<SharePanel {...p} />)
    await userEvent.click(screen.getByLabelText('Make public'))
    expect(p.onShare).toHaveBeenLastCalledWith(true)
    rerender(<SharePanel {...p} isPublic />)
    expect(screen.getByText('Search engines may list this page.')).toBeTruthy()
    await userEvent.click(screen.getByLabelText('Make public'))
    expect(p.onShare).toHaveBeenLastCalledWith(false)
  })
})
