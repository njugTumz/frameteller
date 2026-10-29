import { useCallback, useEffect, useState } from 'react'
import { ApiError, mediaUrl } from '../../../shared/api/client'
import type { GalleryCard, PanelStyle } from '../../../shared/api/types'
import { type GalleryView, heartEntry, listGallery, reportEntry } from '../api'

/** The API's media paths, made absolute for <img> and <video>. */
const playable = (c: GalleryCard): GalleryCard => ({ ...c, cover_url: mediaUrl(c.cover_url) ?? '', video_url: mediaUrl(c.video_url) ?? '' })

const message = (e: unknown) => (e instanceof ApiError ? e.message : 'The gallery did not load. Try again.')

/** The public gallery: one view and style at a time, hearts and reports. */
export function useGallery() {
  const [view, setView] = useState<GalleryView>('featured')
  const [style, setStyle] = useState<PanelStyle | null>(null)
  const [cards, setCards] = useState<GalleryCard[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reported, setReported] = useState<Set<string>>(() => new Set())

  useEffect(() => {
    let live = true
    listGallery(view, style)
      .then((entries) => {
        if (!live) return
        // Nothing featured yet: show the newest instead of an empty page.
        if (entries.length === 0 && view === 'featured' && style === null) setView('newest')
        else {
          setCards(entries.map(playable))
          setError(null)
        }
      })
      .catch((e: unknown) => live && setError(message(e)))
    return () => {
      live = false
    }
  }, [view, style])

  const heart = useCallback(async (id: string) => {
    setCards((all) => all?.map((c) => (c.id === id && !c.hearted ? { ...c, hearted: true, hearts: c.hearts + 1 } : c)) ?? all)
    try {
      const { hearts } = await heartEntry(id)
      setCards((all) => all?.map((c) => (c.id === id ? { ...c, hearts, hearted: true } : c)) ?? all)
    } catch (e) {
      setError(message(e))
    }
  }, [])

  const report = useCallback(async (id: string, reason: string) => {
    try {
      await reportEntry(id, reason)
      setReported((s) => new Set(s).add(id))
    } catch (e) {
      setError(message(e))
    }
  }, [])

  return { view, setView, style, setStyle, cards, error, heart, report, reported }
}
