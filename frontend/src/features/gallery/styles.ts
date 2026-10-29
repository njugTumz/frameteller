import type { PanelStyle } from '../../shared/api/types'

export const STYLE_NAMES: Record<PanelStyle, string> = { pencil: 'Pencil', paper_cutout: 'Paper cutout' }

export function styleName(style: string): string {
  return STYLE_NAMES[style as PanelStyle] ?? style
}
