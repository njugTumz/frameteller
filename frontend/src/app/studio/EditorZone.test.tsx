import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { PanelCanvasProps } from '../../features/panel-editor/components/PanelCanvas'
import { useEditorStore } from '../../features/panel-editor/store'
import { useStoryboardStore } from '../../features/storyboard/store'
import type { Mask } from '../../shared/api/types'
import { panel, project, shot } from '../../test/builders'
import { mockApi } from '../../test/mockApi'
import { EditorZone } from './EditorZone'

// jsdom has no canvas: stand in for react-konva with buttons that click where a test says.
vi.mock('../../features/panel-editor/components/PanelCanvas', () => ({
  PanelCanvas: (p: PanelCanvasProps) => (
    <div>
      <button type="button" onClick={() => p.onPick({ x: 480, y: 160 }, { width: 960, height: 640 })}>
        click the lantern
      </button>
      <button type="button" onClick={() => p.onPick({ x: 150, y: 250 }, { width: 960, height: 640 })}>
        click Mira
      </button>
      <span data-testid="outlined">{p.selected?.mask.label ?? ''}</span>
    </div>
  ),
}))

const mira: Mask = { id: 'character:mira', label: 'Mira', character_id: 'mira', box: { left: 200, top: 300, right: 500, bottom: 1100 }, cutout_url: '/media/projects/p1/m/mira.png' }
const lantern: Mask = { id: 'object:1', label: 'lantern', character_id: null, box: { left: 900, top: 250, right: 1050, bottom: 420 }, cutout_url: '/media/projects/p1/m/lantern.png' }

describe('panel editor: select → mask', () => {
  beforeEach(() => {
    useStoryboardStore.getState().reset()
    useStoryboardStore.getState().load(project({ shots: [shot(1, { panel: panel({ masks: [mira] }) })] }))
    useEditorStore.getState().open('s1', 1)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('sends the click in preview coordinates and outlines the mask SAM found', async () => {
    const api = mockApi({ 'POST /projects/:id/shots/:n/panel/select': () => ({ body: { cached: false, mask: lantern } }) })
    render(<EditorZone projectId="p1" />)
    await userEvent.click(screen.getByRole('button', { name: 'click the lantern' }))
    expect(api.calls.at(-1)).toEqual({ method: 'POST', path: '/projects/p1/shots/1/panel/select', body: { x: 480, y: 160, preview_width: 960, preview_height: 640 } })
    await waitFor(() => expect(screen.getByTestId('outlined').textContent).toBe('lantern'))
    expect(screen.getByTestId('selection-status').textContent).toMatch(/lantern · found in/)
    expect(screen.getByText(/your change applies to lantern/i)).toBeTruthy()
  })

  it('shows a cached character at once, before the server answers', async () => {
    let answer: (v: { body: unknown }) => void = () => undefined
    mockApi({ 'POST /projects/:id/shots/:n/panel/select': () => new Promise((r) => (answer = r)) })
    render(<EditorZone projectId="p1" />)
    await userEvent.click(screen.getByRole('button', { name: 'click Mira' })) // (300, 500) in panel pixels: inside Mira
    expect(screen.getByTestId('outlined').textContent).toBe('Mira')
    expect(screen.getByTestId('selection-status').textContent).toMatch(/Mira · ready instantly/)
    await act(async () => answer({ body: { cached: true, mask: mira } }))
  })

  it('explains an empty click', async () => {
    mockApi({ 'POST /projects/:id/shots/:n/panel/select': () => ({ status: 422, body: { error: { code: 'nothing_to_select', message: 'x' } } }) })
    render(<EditorZone projectId="p1" />)
    await userEvent.click(screen.getByRole('button', { name: 'click the lantern' }))
    expect(await screen.findByText(/nothing to select there/i)).toBeTruthy()
  })

  it('sends an appearance change naming the selection, and shows it is being made', async () => {
    const api = mockApi({
      'POST /projects/:id/shots/:n/panel/select': () => ({ body: { cached: false, mask: lantern } }),
      'POST /projects/:id/shots/:n/panel/edit': () => ({ status: 202, body: { kind: 'edit_panel', key: 'e1', enqueued: true, shot_id: 's1', revision: 2 } }),
    })
    render(<EditorZone projectId="p1" />)
    await userEvent.click(screen.getByRole('button', { name: 'click the lantern' }))
    await screen.findByText(/your change applies to lantern/i)
    await userEvent.type(screen.getByRole('textbox', { name: /change how it looks/i }), 'make it glow green')
    await userEvent.click(screen.getByRole('button', { name: 'Make this change' }))
    await waitFor(() => expect(api.calls.at(-1)?.body).toEqual({ instruction: 'make it glow green (the lantern)' }))
    expect(await screen.findByText('Making your change… about 20 s')).toBeTruthy()
    expect(useEditorStore.getState().before).toEqual({ imageUrl: '/media/projects/p1/panels/s1/r1/image', revision: 1 })
  })
})
