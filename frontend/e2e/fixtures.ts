/** A storyboard panel drawn in SVG, served as /media in the mocked suite. Original art, ours. */
export function panelSvg(n: number): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1280" width="1920" height="1280">
  <rect width="1920" height="1280" fill="#f4f6f8"/>
  <g fill="none" stroke="#9aa8b9" stroke-width="6" stroke-linecap="round">
    <path d="M0 980 C500 960 1400 1000 1920 970"/><path d="M240 980 V420 h360 v560"/><path d="M1380 980 V300 h380 v680"/>
  </g>
  <g stroke="#1c2430" stroke-width="7" stroke-linejoin="round" stroke-linecap="round">
    <circle cx="${880 + n * 20}" cy="520" r="70" fill="#f8fafc"/>
    <path d="M${810 + n * 20} 600 l-60 330 h300 l-60 -330 z" fill="#f2c230"/>
    <path d="M1200 900 q40 -80 110 -40 q60 -40 90 30 q10 70 -60 90 h-90 q-60 -10 -50 -80z" fill="#c3d3e4"/>
  </g>
  <text x="60" y="110" font-family="sans-serif" font-size="64" fill="#556173">shot ${n}</text>
</svg>`
}

export const sheetSvg = (name: string) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" fill="#eef3f8"/><circle cx="256" cy="180" r="70" fill="#f8fafc" stroke="#1c2430" stroke-width="6"/><path d="M190 260 l-40 200 h212 l-40 -200z" fill="#f2c230" stroke="#1c2430" stroke-width="6"/><text x="256" y="500" text-anchor="middle" font-family="sans-serif" font-size="36" fill="#1c2430">${name}</text></svg>`

/** A cut-out for the mocked selection: the figure's coat, transparent around it. */
export const cutoutSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 330" width="300" height="330"><path d="M60 0 l-60 330 h300 l-60 -330 z" fill="#f2c230" stroke="#1c2430" stroke-width="7"/></svg>`
