import { JudgeWelcome } from '../../features/judge/components/JudgeWelcome'
import { useJudgeLink } from '../../features/judge/hooks/useJudgeLink'
import { navigate } from '../router'

export function JudgePage() {
  const state = useJudgeLink()
  return <JudgeWelcome state={state} onStart={() => navigate('/')} />
}
