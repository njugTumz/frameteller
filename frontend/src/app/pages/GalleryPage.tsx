import { useEffect } from 'react'
import { GalleryGrid } from '../../features/gallery/components/GalleryGrid'
import { useGallery } from '../../features/gallery/hooks/useGallery'
import { Button } from '../../shared/ui/Button'
import { navigate } from '../router'

export function GalleryPage() {
  const g = useGallery()
  useEffect(() => {
    document.title = 'Gallery · Frameteller'
  }, [])
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="m-0 text-2xl font-bold">Gallery</h1>
          <p className="m-0 text-muted">Stories people told out loud, drawn and timed by Frameteller.</p>
        </div>
        <Button variant="ink" onClick={() => navigate('/')}>
          Tell your own
        </Button>
      </div>
      <GalleryGrid
        view={g.view}
        style={g.style}
        cards={g.cards}
        error={g.error}
        reported={g.reported}
        onView={g.setView}
        onStyle={g.setStyle}
        onHeart={(id) => void g.heart(id)}
        onReport={(id, reason) => void g.report(id, reason)}
      />
    </div>
  )
}
