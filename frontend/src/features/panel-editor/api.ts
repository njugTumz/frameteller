import { api, call } from '../../shared/api/client'
import type { Selection, Ticket } from '../../shared/api/types'

/** The object under a click on the panel as shown. cached: true means no SAM call was needed (ADR 0006). */
export function selectObject(projectId: string, n: number, point: { x: number; y: number }, preview: { width: number; height: number }): Promise<Selection> {
  return call(() =>
    api.POST('/projects/{project_id}/shots/{n}/panel/select', {
      params: { path: { project_id: projectId, n } },
      body: { x: Math.round(point.x), y: Math.round(point.y), preview_width: Math.round(preview.width), preview_height: Math.round(preview.height) },
    }),
  )
}

export function editPanel(projectId: string, n: number, instruction: string): Promise<Ticket> {
  return call(() => api.POST('/projects/{project_id}/shots/{n}/panel/edit', { params: { path: { project_id: projectId, n } }, body: { instruction } }))
}

/** A spoken instruction (WAV) to text, through Muse Voice Transcribe on the backend. */
export async function dictate(projectId: string, recording: Blob): Promise<string> {
  const result = await call(() =>
    api.POST('/projects/{project_id}/dictation', {
      params: { path: { project_id: projectId } },
      body: recording as unknown as string,
      bodySerializer: (b: unknown) => b as Blob,
      headers: { 'Content-Type': 'audio/wav' },
    }),
  )
  return result.text
}

/** Save a move, resize or delete of a selected object. The backend composites it on a clean plate (ADR 0010). */
export function saveLayer(projectId: string, n: number, objectId: string, move: { dx: number; dy: number; scale: number }, deleted = false): Promise<Ticket> {
  return call(() =>
    api.POST('/projects/{project_id}/shots/{n}/panel/layers', {
      params: { path: { project_id: projectId, n } },
      body: { object_id: objectId, dx: move.dx, dy: move.dy, scale: move.scale, deleted },
    }),
  )
}
