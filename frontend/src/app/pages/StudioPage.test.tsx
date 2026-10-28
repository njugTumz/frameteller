import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useStoryboardStore } from '../../features/storyboard/store'
import { character, panel, project, shot } from '../../test/builders'
import { mockApi } from '../../test/mockApi'
import { dispatchEvent } from '../studio/dispatch'
import { StudioPage } from './StudioPage'

const ticket = (n: number) => ({ kind: 'generate_panel', key: `k${n}`, enqueued: true, shot_id: `s${n}`, revision: 1 })

describe('studio: cast approval gates the panels', () => {
  let served = project({ cast: { status: 'draft', characters: [character('mira')] }, shots: [shot(1), shot(2)] })

  beforeEach(() => {
    served = project({ cast: { status: 'draft', characters: [character('mira')] }, shots: [shot(1), shot(2)] })
  })
  afterEach(() => vi.unstubAllGlobals())

  it('draws nothing until the cast is approved, then a draft for every shot, then shows the panel', async () => {
    const api = mockApi({
      'GET /projects/:id': () => ({ body: served }),
      'POST /projects/:id/cast/approve': () => ({ body: { approved: true, redrawing: [], job_key: null } }),
      'POST /projects/:id/shots/:n/panel': (c) => ({ status: 202, body: ticket(Number(c.path.split('/')[4])) }),
    })
    render(<StudioPage projectId="p1" />)

    expect(await screen.findAllByText('Waiting for the cast')).toHaveLength(2)
    expect(screen.getAllByText(/panels are drawn once you approve the cast/i)).toHaveLength(2)
    const renders = () => api.calls.filter((c) => c.method === 'POST' && c.path.endsWith('/panel'))
    expect(renders()).toHaveLength(0)

    await userEvent.click(screen.getByRole('button', { name: 'Approve cast' }))
    await waitFor(() => expect(renders().map((c) => [c.path, c.body])).toEqual([
      ['/projects/p1/shots/1/panel', { quality: 'draft' }],
      ['/projects/p1/shots/2/panel', { quality: 'draft' }],
    ]))
    expect(await screen.findAllByText('In the queue')).toHaveLength(2)

    act(() => dispatchEvent({ type: 'job.updated', kind: 'generate_panel', key: 'k1', status: 'running', shot_id: 's1', revision: 1, message: null }))
    expect(screen.getByText('Drawing draft…')).toBeTruthy()

    served = { ...served, cast: { ...served.cast, status: 'approved' }, shots: [shot(1, { panel: panel() }), shot(2)] }
    act(() => dispatchEvent({ type: 'job.updated', kind: 'generate_panel', key: 'k1', status: 'succeeded', shot_id: 's1', revision: 1, message: null }))
    const image = await screen.findByRole('img', { name: /shot 1/i })
    expect(image.getAttribute('src')).toBe('http://localhost:8000/media/projects/p1/panels/s1/r1/image')
    expect(renders()).toHaveLength(2) // a refresh never asks for the same draft twice
  })

  it('holds Approve cast back, with the reason, while a sheet is still being drawn', async () => {
    mockApi({ 'GET /projects/:id': () => ({ body: served }) })
    render(<StudioPage projectId="p1" />)
    await screen.findAllByText('Waiting for the cast')
    act(() => dispatchEvent({ type: 'shot.created', shot: shot(3, { character_ids: ['grey_cat'] }) }))
    expect(screen.getByRole('button', { name: 'Approve cast' })).toHaveProperty('disabled', true)
    expect(screen.getByText(/still being drawn/i)).toBeTruthy()
    expect(screen.getByText('Drawing sheets for Grey cat…')).toBeTruthy()

    act(() => dispatchEvent({ type: 'cast.proposed', characters: [character('grey_cat', { name: 'Grey Cat' })] }))
    expect(screen.getByRole('button', { name: 'Approve cast' })).toHaveProperty('disabled', false)
    expect(screen.getByRole('img', { name: 'Reference sheet for Grey Cat' })).toBeTruthy()
    expect(useStoryboardStore.getState().shots).toHaveLength(3)
  })

  it('sends edited descriptions with the approval and waits for the redrawn sheet', async () => {
    const api = mockApi({
      'GET /projects/:id': () => ({ body: served }),
      'POST /projects/:id/cast/approve': () => ({ body: { approved: false, redrawing: ['mira'], job_key: 'cast-2' } }),
    })
    render(<StudioPage projectId="p1" />)
    const description = await screen.findByRole('textbox', { name: 'Description of Mira' })
    await userEvent.clear(description)
    await userEvent.type(description, 'a girl in a red raincoat')
    await userEvent.click(screen.getByRole('button', { name: 'Approve cast' }))
    await waitFor(() => expect(api.calls.find((c) => c.path.endsWith('/approve'))?.body).toEqual({ descriptions: { mira: 'a girl in a red raincoat' } }))
    expect(await screen.findByText('Redrawing Mira…')).toBeTruthy()
    expect(screen.getAllByText('Waiting for the cast')).toHaveLength(2)
  })
})
