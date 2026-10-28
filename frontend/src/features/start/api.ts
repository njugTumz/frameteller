import { api, call } from '../../shared/api/client'
import type { PanelStyle, Project } from '../../shared/api/types'

export function createProject(title: string, style: PanelStyle): Promise<Project> {
  return call(() => api.POST('/projects', { body: { title, style } }))
}
