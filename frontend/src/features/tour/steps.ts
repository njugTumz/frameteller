import { DEFAULT_VOICE } from '../script/store'

/**
 * The guided tour runs on the real "Try a sample story" (Read it to me, the rooftop script, Ava). Each step points
 * at a real element. A step is ready when its element exists, and the studio shows those elements only once the
 * session events behind them arrive (a shot directed, a cast proposed, a review, a panel drawn), so the tour follows
 * the story, never a timer. Steps that need the visitor (approving the cast, selecting an object) move on by
 * themselves when the result appears.
 */
export interface TourStep {
  id: string
  page: 'start' | 'studio'
  title: string
  body: string
  /** CSS selector of the element the card points at; none: a centred card. */
  anchor?: string
  /** Until the anchor exists: what is happening, roughly how long, and where to point meanwhile. */
  waitFor?: { text: string; seconds?: number; anchor?: string }
  /** The visitor's turn: the tour moves on once this selector matches. */
  doneWhen?: { selector: string; prompt: string }
  /** Hidden behind something (the panel editor): say what to do. */
  blockedBy?: { selector: string; text: string }
  /** The Next button does this instead (start the sample story, or go narrate). */
  action?: { kind: 'start-sample' | 'narrate'; label: string }
}

const READY_PANEL = '[data-testid="shot-card"][data-phase="ready"]'
const EDITOR_OPEN = { selector: '[data-testid="panel-editor"]', text: 'Close the panel editor to see this.' }

export const TOUR_STEPS: TourStep[] = [
  {
    id: 'modes',
    page: 'start',
    anchor: '[data-tour="modes"]',
    title: 'Three ways to tell a story',
    body: 'Narrate it out loud, read your script from a teleprompter, or have a voice read it to you. This tour uses Read it to me, with our sample story.',
  },
  {
    id: 'voice',
    page: 'start',
    anchor: `[data-voice="${DEFAULT_VOICE}"]`,
    waitFor: { text: 'Loading the voices…', seconds: 5 },
    title: "This one's Ava",
    body: 'Ava reads the sample story a paragraph at a time, with Azure Text-to-Speech. Preview any voice; each one speaks nine languages.',
    action: { kind: 'start-sample', label: 'Start the sample story' },
  },
  {
    id: 'script',
    page: 'studio',
    anchor: '[data-testid="teleprompter"]',
    waitFor: { text: 'Press Read it to me. Ava starts within a few seconds.', anchor: '[data-tour="reading"]' },
    title: 'The script, as it is read',
    body: 'The paragraph being read is highlighted. Each paragraph becomes a shot.',
  },
  {
    id: 'shot',
    page: 'studio',
    anchor: '[data-testid="shot-card"]',
    waitFor: { text: 'Muse Spark is directing the first paragraph.', seconds: 10 },
    title: 'Muse Spark directs each paragraph into a shot',
    body: 'Framing, characters, setting and action, on a shot card. Its panel is drawn once the cast is approved.',
  },
  {
    id: 'cast',
    page: 'studio',
    anchor: '[data-testid="cast-tray"]',
    waitFor: { text: 'Muse Spark is finding the characters.', seconds: 15 },
    doneWhen: { selector: '[data-testid="cast-tray"][data-status="approved"]', prompt: 'Check the sheets, then click Approve cast.' },
    title: 'Muse Image draws a reference sheet per character',
    body: 'Every panel copies these sheets, so this is the place to fix a character.',
  },
  {
    id: 'supervisor',
    page: 'studio',
    anchor: '[data-testid="review-badge"]',
    waitFor: { text: 'The supervisor is checking the first sheet.', seconds: 20 },
    title: 'An agent checks every sheet and panel against its rubric',
    body: 'Muse Glimmer when warm, Muse Spark otherwise. A tick means it passed; if something is off, it fixes it or asks you.',
  },
  {
    id: 'panels',
    page: 'studio',
    anchor: READY_PANEL,
    waitFor: { text: 'Muse Image is drawing the first panels.', seconds: 30 },
    title: 'Muse Image draws with the approved cast',
    body: "Draft panels draw themselves, with the cast sheets as references, so each character looks the same in every panel. Don't like a frame? Redraw it, and say what should change.",
  },
  {
    id: 'select',
    page: 'studio',
    anchor: '[data-testid="panel-canvas"]',
    waitFor: { text: 'Click a drawn panel to open it.', anchor: READY_PANEL },
    doneWhen: { selector: '[data-testid="selection-status"][data-selected]', prompt: 'Click a character or object in the panel.' },
    title: 'SAM 3.1 selects it',
    body: 'Click anything in the panel and SAM 3.1 cuts it out: drag it to move it, or change just that object.',
  },
  {
    id: 'edit',
    page: 'studio',
    anchor: '[data-tour="edit-box"]',
    waitFor: { text: 'Open a drawn panel to edit it.', anchor: READY_PANEL },
    title: 'Change how it looks',
    body: 'Type or say a change, like “make her coat red”. Muse Image redraws the panel from the stored image and the cast sheets, keeping the layout.',
  },
  {
    id: 'export',
    page: 'studio',
    anchor: '[data-testid="export-panel"]',
    blockedBy: EDITOR_OPEN,
    title: 'Export an animatic, with captions',
    body: "Each panel lasts as long as its paragraph, with Ava's voice and captions of what is said, in the picture and as subtitles. It is ready once every panel is drawn. Press Play with sound to hear it, and Listen to your narration to hear what you recorded.",
  },
  {
    id: 'share',
    page: 'studio',
    anchor: '[data-testid="share-panel"]',
    blockedBy: EDITOR_OPEN,
    title: 'Share it, or put it in the gallery',
    body: 'A read-only link previews nicely on X. Submit to gallery publishes it after an automatic check.',
  },
  {
    id: 'narrate',
    page: 'studio',
    title: 'Now tell your own',
    body: 'Choose Narrate and just talk: Muse Voice Transcribe listens as you talk, and each pause becomes a shot.',
    action: { kind: 'narrate', label: 'Narrate a story' },
  },
]
