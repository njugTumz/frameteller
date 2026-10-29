import type { Character, Panel, Project, Review, Shot, SupervisorEntry, Turn } from '../shared/api/types'
import type { ServerEvent } from '../shared/events'

export function turn(n: number, text = `words of beat ${n}`, over: Partial<Turn> = {}): Turn {
  return { id: `t-b${n}`, text, start_ms: (n - 1) * 5000, end_ms: n * 5000, speaker: null, direction: '', episode: 1, ...over }
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
    episode: 1,
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
    share_public: false,
    continuity_checks: true,
    supervisor: [],
    ...over,
  }
}

export const ev = (e: ServerEvent): ServerEvent => e

export function review(over: Partial<Review> = {}): Review {
  return {
    outcome: 'checked',
    summary: 'Checked',
    issues: [],
    fix_instruction: '',
    model: 'muse-glimmer',
    confidence: 0.9,
    fixes: 0,
    rubrics: { 'panel-continuity': 'abc123def456' },
    ...over,
  }
}

export function supervisorEntry(over: Partial<SupervisorEntry> = {}): SupervisorEntry {
  return {
    at: '2026-10-29T12:00:00+00:00',
    subject: 'Shot 4',
    outcome: 'fixed',
    message: 'Shot 4: remove the blue vest (CONT-04, Pip wears a blue vest that is not on his reference sheet). Fixed in 1 try.',
    rule_ids: ['CONT-04'],
    model: 'muse-spark-1.3',
    shot_id: 's4',
    character_id: null,
    ...over,
  }
}
