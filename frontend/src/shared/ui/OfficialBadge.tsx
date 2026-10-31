/** Next to the byline of an entry the admin signed or published with a reserved name ("Frameteller team"). */
export function OfficialBadge() {
  return (
    <span
      className="ml-2 inline-block rounded-full bg-marker px-2 py-0.5 align-middle text-xs font-extrabold text-ink ring-1 ring-ink"
      data-testid="official-badge"
      title="Published by the Frameteller team"
    >
      Official
    </span>
  )
}
