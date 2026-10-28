import type { Character, Panel, Project, Shot, Turn } from '../shared/api/types'
import type { ServerEvent } from '../shared/events'

export function turn(n: number, text = `words of beat ${n}`, over: Partial<Turn> = {}): Turn {
  return { id: `t-b${n}`, text, start_ms: (n - 1) * 5000, end_ms: n * 5000, speaker: null, ...over }
}

export function shot(n: number, over: Partial<Shot> = {}): Shot {
  return {
    id: `s${n}`,
    number: n,
    framing: 'medium',
    character_ids: ['mira'],
    setting: 'a rainy alley at night',
    action: `Mira does thing ${n}`,
    dialogue: '',
    duration_ms: 5000,
    source_turn_ids: [`t-b${n}`],
    panel: null,
    ...over,
  }
}

export function panel(over: Partial<Panel> = {}): Panel {
  return {
    revision: 1,
    shown_revision: 1,
    status: 'ready',
    image_url: '/media/projects/p1/panels/s1/r1/image',
    base_image_url: '/media/projects/p1/panels/s1/r1/image',
    width: 1920,
    height: 1280,
    masks: [],
    layers: [],
    outdated: false,
    ...over,
  }
}

export function character(id = 'mira', over: Partial<Character> = {}): Character {
  return { id, name: id.charAt(0).toUpperCase() + id.slice(1), description: `${id}, an original character`, reference_url: `/media/projects/p1/characters/${id}/reference`, ...over }
}

export function project(over: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    title: 'The Lantern Cat',
    style: 'pencil',
    cast: { status: 'draft', characters: [] },
    turns: [],
    shots: [],
    narrations: [],
    animatic: null,
    share_token: null,
    ...over,
  }
}

export const ev = (e: ServerEvent): ServerEvent => e
