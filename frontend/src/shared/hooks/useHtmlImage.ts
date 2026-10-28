import { useEffect, useState } from 'react'

/** Load an image for a canvas. No crossOrigin: we only draw it, never read its pixels back. */
export function useHtmlImage(src: string | null): HTMLImageElement | null {
  const [loaded, setLoaded] = useState<{ src: string; image: HTMLImageElement } | null>(null)
  useEffect(() => {
    if (!src) return
    const image = new Image()
    image.decoding = 'async'
    image.onload = () => setLoaded({ src, image })
    image.src = src
    return () => {
      image.onload = null
    }
  }, [src])
  return loaded && loaded.src === src ? loaded.image : null
}
