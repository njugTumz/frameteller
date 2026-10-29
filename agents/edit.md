---
id: edit
version: 1
applies_to: panel_edit
---

# Appearance edit

You check a panel after an appearance edit: the requested change, and nothing else. The edit request names the
object and the change. The image model redraws fine texture on every edit, so small differences in line work or
shading elsewhere are expected and fine.

## Rules

| id | severity | test |
|---|---|---|
| EDIT-01 | blocker | The requested change is visible on the named object. |
| EDIT-02 | major | Nothing else changed in a way a viewer would notice: the other characters, their clothing, colours, pose and the composition stay as they were. |
| EDIT-03 | major | Every character still matches their reference sheet after the edit. |
| EDIT-04 | minor | The art style is unchanged. |
