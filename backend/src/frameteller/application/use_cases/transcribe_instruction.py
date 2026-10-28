from __future__ import annotations

from frameteller.application.ports import ProjectRepository, SpeechOptions, SpeechToTextPort

MAX_DICTATION_MS = 30_000


class TranscribeInstruction:
    """A short spoken instruction from the panel editor ("make her raincoat red") to text for the user to review.

    Nothing is directed: the text goes back to the editor, which sends it as an edit once the user agrees.
    The cast's names bias recognition, as in a live session.
    """

    def __init__(self, repo: ProjectRepository, speech: SpeechToTextPort) -> None:
        self._repo, self._speech = repo, speech

    async def execute(self, project_id: str, wav: bytes) -> str:
        project = await self._repo.get(project_id)
        names = tuple(c.name for c in project.bible.characters.values())
        turns = await self._speech.transcribe_file(wav, SpeechOptions(keywords=names))
        return " ".join(t.text.strip() for t in turns if t.text.strip())
