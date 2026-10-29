import { beforeEach, describe, expect, it } from 'vitest'
import { DEFAULT_CHOICE } from './store'
import { loadChoice, readScriptFile, saveChoice, scriptFormat } from './choice'

describe('scriptFormat', () => {
  it.each([
    ['Lena waves.', '', 'text'],
    ['Lena waves.', 'roof.md', 'markdown'],
    ['Lena waves.', 'ROOF.FOUNTAIN', 'fountain'],
    ['INT. ROOFTOP - NIGHT\n\nLena waves.', '', 'fountain'],
    ['EXT. HARBOUR - DAY', 'notes.txt', 'fountain'],
  ])('%j from %j is %s', (text, name, format) => {
    expect(scriptFormat(text, name)).toBe(format)
  })
})

describe('the telling choice', () => {
  beforeEach(() => window.localStorage.clear())

  it('is kept per story and falls back to narrating', () => {
    expect(loadChoice('p1')).toEqual(DEFAULT_CHOICE)
    const choice = { mode: 'read' as const, script: 'Lena waves.', format: 'text' as const, voice: 'en-GB-AdaMultilingualNeural', language: 'fr-FR' }
    saveChoice('p1', choice)
    expect(loadChoice('p1')).toEqual(choice)
    window.localStorage.setItem('frameteller.telling.p2', '{"mode":"sing"}')
    expect(loadChoice('p2').mode).toBe('narrate')
  })
})

describe('readScriptFile', () => {
  it('reads plain text scripts and refuses other files', async () => {
    const fountain = new File(['INT. ROOF - NIGHT\n\nLena waves.'], 'roof.fountain', { type: 'text/plain' })
    expect(await readScriptFile(fountain)).toEqual({ text: 'INT. ROOF - NIGHT\n\nLena waves.', format: 'fountain' })
    await expect(readScriptFile(new File(['x'], 'roof.docx'))).rejects.toThrow(/paste it here/)
  })
})
