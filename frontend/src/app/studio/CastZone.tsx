import { CastTray } from '../../features/cast/components/CastTray'
import { CharacterCard } from '../../features/cast/components/CharacterCard'
import { useCastReview } from '../../features/cast/hooks/useCastReview'
import { approvalBlock, nameFromId, useCastStore } from '../../features/cast/store'
import { mediaUrl } from '../../shared/api/client'

export function CastZone({ projectId }: { projectId: string }) {
  const cast = useCastStore()
  const { approve, regenerate, edit } = useCastReview(projectId)
  if (cast.characters.length === 0 && cast.expected.length === 0) return null
  const locked = cast.status === 'approved'
  return (
    <CastTray
      status={cast.status}
      block={approvalBlock(cast)}
      approving={cast.approving}
      pending={cast.expected.map(nameFromId)}
      error={cast.error}
      onApprove={() => void approve()}
      onChange={() => cast.set({ status: 'draft' })}
    >
      {cast.characters.map((c) => (
        <CharacterCard
          key={c.id}
          character={c}
          imageSrc={mediaUrl(c.reference_url)}
          description={cast.edits[c.id] ?? c.description}
          redrawing={!!cast.redrawing[c.id]}
          locked={locked}
          onDescribe={(text) => edit(c.id, text)}
          onRegenerate={() => void regenerate(c.id)}
        />
      ))}
    </CastTray>
  )
}
