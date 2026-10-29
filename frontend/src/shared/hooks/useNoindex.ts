import { useEffect } from 'react'

/**
 * Ask search engines to leave this page out while `active`, with a robots meta tag. It never relaxes a noindex
 * the build already put in index.html (staging is never indexed, STUDIO_NOINDEX=1), and removes only its own tag.
 */
export function useNoindex(active: boolean) {
  useEffect(() => {
    if (!active || document.head.querySelector('meta[name="robots"]')) return
    const meta = document.createElement('meta')
    meta.name = 'robots'
    meta.content = 'noindex, nofollow'
    document.head.append(meta)
    return () => meta.remove()
  }, [active])
}
