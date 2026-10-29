import type { Shot } from '../../shared/api/types'

export interface EpisodeShots {
  episode: number
  shots: Shot[]
  /** The same shots numbered from 1 within the episode, for display. */
  numbered: Shot[]
}

/** Shots grouped by episode, in story order; numbering restarts in each episode (ADR 0015). */
export function byEpisode(shots: Shot[]): EpisodeShots[] {
  const groups = new Map<number, Shot[]>()
  for (const s of shots) groups.set(s.episode, [...(groups.get(s.episode) ?? []), s])
  return [...groups.entries()]
    .sort(([a], [b]) => a - b)
    .map(([episode, list]) => ({ episode, shots: list, numbered: list.map((s, i) => ({ ...s, number: i + 1 })) }))
}
