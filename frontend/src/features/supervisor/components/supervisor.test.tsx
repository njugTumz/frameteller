import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ReviewIssue } from '../../../shared/api/types'
import { review, supervisorEntry } from '../../../test/builders'
import { NeedsYourEye } from './NeedsYourEye'
import { ReviewBadge } from './ReviewBadge'
import { SupervisorFeed } from './SupervisorFeed'

const VEST: ReviewIssue = { rule_id: 'CONT-04', severity: 'major', description: 'Pip wears a blue vest that is not on his reference sheet' }

describe('ReviewBadge', () => {
  it.each([
    [review(), 'Checked'],
    [review({ outcome: 'fixed', summary: 'Fixed: remove the blue vest' }), 'Fixed: remove the blue vest'],
    [review({ outcome: 'needs_user', issues: [VEST] }), 'Needs your eye'],
    [review({ outcome: 'accepted' }), 'Accepted'],
  ])('says what the supervisor did', (r, label) => {
    render(<ReviewBadge review={r} />)
    expect(screen.getByTestId('review-badge').textContent).toContain(label)
  })

  it('names the model that checked it', () => {
    render(<ReviewBadge review={review({ model: 'muse-glimmer' })} />)
    expect(screen.getByTestId('review-badge').getAttribute('aria-label')).toBe('Checked. Checked by Muse Glimmer')
    expect(screen.getByTestId('review-badge').getAttribute('title')).toBe('Checked by Muse Glimmer')
  })
})

describe('NeedsYourEye', () => {
  it('lists the serious issues and offers the fix, accept and redraw', async () => {
    const onApply = vi.fn()
    const onAccept = vi.fn()
    const onRedraw = vi.fn()
    const minor: ReviewIssue = { rule_id: 'CONT-08', severity: 'minor', description: 'tail a shade lighter' }
    render(
      <NeedsYourEye
        review={review({ outcome: 'needs_user', issues: [VEST, minor], fix_instruction: 'remove the blue vest', model: 'muse-spark-1.3' })}
        busy={false}
        onApply={onApply}
        onAccept={onAccept}
        onRedraw={onRedraw}
      />,
    )
    expect(screen.getByText(/blue vest that is not on his reference sheet/)).toBeTruthy()
    expect(screen.queryByText(/a shade lighter/)).toBeNull()
    expect(screen.getByText('Suggested fix: remove the blue vest')).toBeTruthy()
    expect(screen.getByText('Checked by Muse Spark')).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: 'Apply suggested fix' }))
    await userEvent.click(screen.getByRole('button', { name: 'Accept anyway' }))
    await userEvent.click(screen.getByRole('button', { name: 'Redraw' }))
    expect([onApply, onAccept, onRedraw].map((f) => f.mock.calls.length)).toEqual([1, 1, 1])
  })

  it('offers no fix when an edit cannot repair it', () => {
    render(<NeedsYourEye review={review({ outcome: 'needs_user', issues: [VEST] })} busy={false} onApply={vi.fn()} onAccept={vi.fn()} />)
    expect(screen.queryByRole('button', { name: 'Apply suggested fix' })).toBeNull()
    expect((screen.getByRole('button', { name: 'Accept anyway' }) as HTMLButtonElement).disabled).toBe(false)
  })
})

describe('SupervisorFeed', () => {
  it('lists the decisions in order and toggles the checks', async () => {
    const onToggle = vi.fn()
    const entries = [supervisorEntry({ message: 'Shot 1: checked, no continuity issues.', outcome: 'checked', model: 'muse-glimmer' }), supervisorEntry()]
    render(<SupervisorFeed entries={entries} enabled busy={false} error={null} onToggle={onToggle} />)
    const items = screen.getAllByRole('listitem')
    expect(items[0]?.textContent).toContain('Shot 1: checked, no continuity issues. (Muse Glimmer)')
    expect(items[1]?.textContent).toContain('Shot 4: remove the blue vest (CONT-04')
    await userEvent.click(screen.getByRole('checkbox', { name: 'Continuity checks' }))
    expect(onToggle).toHaveBeenCalledWith(false)
  })

  it('explains itself before the first decision', () => {
    render(<SupervisorFeed entries={[]} enabled={false} busy={false} error={null} onToggle={vi.fn()} />)
    expect(screen.getByText(/Checks are off/)).toBeTruthy()
  })
})
