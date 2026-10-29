import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { GalleryCard } from '../../../shared/api/types'
import { GalleryCardView } from './GalleryCardView'

const card: GalleryCard = {
  id: 'g1',
  title: 'The Kite Maker',
  style: 'paper_cutout',
  episodes: 2,
  shots: 8,
  duration_ms: 42000,
  cover_url: 'https://api.example/gallery/g1/cover.webp',
  video_url: 'https://api.example/gallery/g1/video.mp4',
  share_url: 'https://app.example/s/tok',
  hearts: 3,
  hearted: false,
  featured: true,
  published_at: '2026-11-02T17:00:00Z',
}

describe('GalleryCardView', () => {
  it('plays the animatic in place of the cover, and links to the share page', async () => {
    render(<GalleryCardView card={card} reported={false} onHeart={vi.fn()} onReport={vi.fn()} />)
    expect(screen.getByText(/Paper cutout · 2 episodes · 8 shots/)).toBeTruthy()
    expect(screen.getByRole('link', { name: 'The Kite Maker' }).getAttribute('href')).toBe(card.share_url)
    await userEvent.click(screen.getByRole('button', { name: 'Play The Kite Maker' }))
    expect(screen.getByLabelText('The Kite Maker, the animatic').getAttribute('src')).toBe(card.video_url)
  })

  it('hearts once and reports with a reason', async () => {
    const onHeart = vi.fn()
    const onReport = vi.fn()
    const { rerender } = render(<GalleryCardView card={card} reported={false} onHeart={onHeart} onReport={onReport} />)
    await userEvent.click(screen.getByRole('button', { name: /3 hearts/ }))
    expect(onHeart).toHaveBeenCalledOnce()
    rerender(<GalleryCardView card={{ ...card, hearted: true, hearts: 4 }} reported={false} onHeart={onHeart} onReport={onReport} />)
    expect(screen.getByRole('button', { name: /4 hearts/ }).getAttribute('aria-pressed')).toBe('true')
    await userEvent.click(screen.getByRole('button', { name: 'Report' }))
    await userEvent.type(screen.getByLabelText('What’s wrong with it?'), 'a real person')
    await userEvent.click(screen.getByRole('button', { name: 'Send report' }))
    expect(onReport).toHaveBeenCalledWith('a real person')
  })
})
