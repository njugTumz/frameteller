import { CastTray } from '../../features/cast/components/CastTray'
import { CharacterCard } from '../../features/cast/components/CharacterCard'
import { useCastManage } from '../../features/cast/hooks/useCastManage'
import { useCastReview } from '../../features/cast/hooks/useCastReview'
import { approvalBlock, nameFromId, useCastStore } from '../../features/cast/store'
import { mediaUrl } from '../../shared/api/client'
import type { Project } from '../../shared/api/types'

export function CastZone({ projectId, onProject }: { projectId: string; onProject: (p: Project) => void }) {
  const cast = useCastStore()
  const { approve, regenerate, edit } = useCastReview(projectId)
  const manage = useCastManage(projectId, onProject)
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
          others={cast.characters.filter((o) => o.id !== c.id)}
          busy={cast.managing}
          onRename={(name) => manage.rename(c.id, name)}
          onRemove={() => manage.remove(c.id)}
          onMerge={(into) => manage.merge(c.id, into)}
        />
      ))}
    </CastTray>
  )
}
