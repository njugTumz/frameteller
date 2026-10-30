/** The plainer description offered after Muse Image refused a sheet twice (ADR 0019). */
export function Suggestion({ text }: { text: string }) {
  return (
    <p className="m-0 rounded border-[1.5px] border-rule bg-paper px-2 py-1 text-left text-xs" data-testid="sheet-suggestion">
      <span className="font-bold">Try: </span>
      {text}
    </p>
  )
}
