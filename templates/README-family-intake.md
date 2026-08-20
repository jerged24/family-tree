# Family intake sheet — how it works

This folder holds the shared-sheet workflow for collecting family information from
relatives (who fill it on their phones) and loading it into the Family Tree app.

## Files

- **`family_intake_template.csv`** — the column layout. The header row is what the
  app's **Import spreadsheet** button understands. The three example rows show the
  expected style; delete them before real use.

## The columns

| Column | Required? | Example | Notes |
|---|---|---|---|
| First name | yes* | Maria | *at least First or Last is needed |
| Last name | yes* | Gedorio | |
| Sex | no | M or F | also accepts Male / Female |
| Date of birth | no | `12 Jun 1940`, `about 1945`, `1970` | free text; approximate is fine |
| Birth place | no | Cebu | |
| Date of death | no | *(blank if living)* | leave empty for living people |
| Father's full name | no | Juan Gedorio | used to link the tree by name |
| Mother's full name | no | Ana Reyes | used to link the tree by name |
| Spouse's full name | no | Pedro Cruz | used to link the tree by name |
| Notes | no | anything | optional |

Extra columns (e.g. a Google Forms **Timestamp** or **Email**) are ignored, so a
Google Form's exported sheet imports as-is.

## How linking works

- Father / Mother / Spouse are matched **by name** against everyone already in the
  tree plus everyone else in the same upload.
- A parent or spouse who is **named but has no row of their own** is added as a
  **name-only entry** so the tree still connects — you can flesh them out later, or a
  future row for them can be merged in with the app's **Find duplicates** tool.
- A name that matches **two people** is left unlinked and reported after import, so
  you can fix it by hand instead of it guessing wrong.

## Owner steps (you)

1. Put `family_intake_template.csv` into a Google Sheet (or build a Google Form from
   these columns) and share it to the family group chat.
2. When it's filled, export/download it as **CSV**.
3. In the app, click **Import spreadsheet** and pick that CSV.
4. Review the summary + any notes, then tidy up with **Find duplicates** and add
   photos per person.

Photos aren't collected in the sheet — have relatives post them in the group chat and
add them yourself in the app (drag-and-drop onto a person).
