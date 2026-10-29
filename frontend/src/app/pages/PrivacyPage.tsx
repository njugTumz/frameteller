import { APP_NAME } from '../../config'

/** What the studio keeps, why, and for how long. Plain words; linked from the start screen and the marketing site. */
export function PrivacyPage() {
  return (
    <article className="mx-auto w-full max-w-2xl px-4 py-10 md:py-16 [&_h2]:mt-10 [&_h2]:mb-3 [&_h2]:text-2xl [&_h2]:font-extrabold [&_li]:mt-2 [&_p]:mt-3 [&_ul]:pl-5 [&_ul]:list-disc">
      <h1 className="m-0 text-4xl font-black tracking-tight widest md:text-5xl">Privacy</h1>
      <p className="text-lg text-muted">
        {APP_NAME} turns a story you tell out loud into a storyboard. Here is everything it keeps, and for how long.
      </p>

      <h2>No accounts, no tracking</h2>
      <p>
        There are no accounts and no tracking or advertising cookies. Your browser keeps a random id and a few
        preferences (your theme, whether to keep your narration) in its own storage. The id is sent with each request
        so the public demo can limit how many stories one visitor starts a day. For that count we store only a
        one-way hash of the id together with your IP address.
      </p>

      <h2>What we store, and why</h2>
      <ul>
        <li>
          <strong>Your story:</strong> its title, the transcript of what you said, the shots, the cast and every panel
          drawn for it. That is the storyboard itself, so you can come back to it.
        </li>
        <li>
          <strong>Your recording, only if you choose to keep it:</strong> it becomes the voice track of your animatic.
          Untick "Keep my narration" before you start, or press <strong>Delete my recording</strong> in the studio at
          any time, and it is deleted straight away. Your storyboard stays.
        </li>
        <li>
          <strong>Exports and share links:</strong> the animatic and PDF you export, and a share link if you make one.
          A share link is unlisted unless you choose "Make public", and you can turn it off at any time.
        </li>
        <li>
          <strong>Operational logs:</strong> each request's time, address and outcome, errors and model costs, so we
          can keep the studio running and stop abuse. They never contain your audio, and they are deleted after 30
          days.
        </li>
      </ul>
      <p>
        Everything is stored privately in Microsoft Azure (East US 2). Anyone with the link to a story's studio page
        can edit it, so keep that link to yourself and share the read-only share link instead.
      </p>

      <h2>Deleted after 30 days</h2>
      <p>
        Stories, recordings, panels, exports and share links are deleted automatically 30 days after they were last
        changed.
      </p>

      <h2>Meta's models, in standard mode</h2>
      <p>
        Your speech is transcribed by Meta's Muse Voice Transcribe, your story is directed by Muse Spark, panels are
        drawn by Muse Image and objects are selected by SAM, all through Meta's Model API. The public studio uses
        Meta's standard mode, which does not use your content to train Meta's models. Your browser never talks to
        Meta directly: every request goes through our backend.
      </p>

      <h2>Original stories only</h2>
      <p>
        Please tell stories with characters of your own. The studio declines real, named people and well-known
        characters from films, books and games, and asks you for an original character instead.
      </p>
    </article>
  )
}
