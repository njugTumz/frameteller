# Rubrics for the continuity supervisor

One markdown file per pipeline step. The backend loads them at runtime (ADR 0012), sends the rules to the
reviewer model, and records each file's hash with every verdict, so a decision can always be traced to the exact
rubric text that produced it.

| File | Checks | When |
|---|---|---|
| [cast.md](cast.md) | a character's reference sheet against its description | before the cast is approved |
| [panel-continuity.md](panel-continuity.md) | every character in a panel against their reference sheet | after every draft and final render |
| [shot.md](shot.md) | the panel against its shot: framing, cast, action, setting | with panel-continuity |
| [edit.md](edit.md) | an appearance edit against what was asked | after a fix or a spoken edit |
| [gallery.md](gallery.md) | a storyboard before the public gallery shows it (ADR 0017) | on "Submit to gallery" |

Format: front matter (`id`, `version`, `applies_to`), a short guidance section the reviewer reads, then one table
row per rule: a stable id (never reused or renumbered), a severity and a one-line test.

- **blocker**: the panel tells the wrong story (a missing or extra character, the wrong species).
- **major**: a visible continuity break a viewer would notice (added clothing, wrong colours, another art style).
- **minor**: worth noting, never worth a redraw on its own.

Only blocker and major issues trigger a fix or a question to the user. Change a rule's wording freely (the hash
records it); add a new rule with a new id; retire a rule by deleting its row, never by reusing its id.
