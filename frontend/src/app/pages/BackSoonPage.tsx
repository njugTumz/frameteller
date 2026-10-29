/** DEMO_PAUSED: the kill switch. Shared storyboards keep working; everything else waits here. */
export function BackSoonPage() {
  return (
    <div className="mx-auto w-full max-w-xl px-4 py-16 md:py-24">
      <h1 className="m-0 text-4xl font-black tracking-tight widest md:text-5xl">Back soon.</h1>
      <p className="mt-5 text-lg text-muted">
        Frameteller is taking a short break. Your storyboards are saved, and shared links still open. Come back in a
        little while.
      </p>
    </div>
  )
}
