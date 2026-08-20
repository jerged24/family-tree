# Family intake sheet — how it works

This folder holds the shared-sheet workflow for collecting family information from
relatives (who fill it on their phones) and loading it into the Family Tree app.

## Files

- **`family_intake_template.csv`** — the column layout. The header row is what the
  app's **Import spreadsheet** button understands. The three example rows show the
  expected style; delete them before real use.

## ⭐ The one naming rule (tell every relative)

**For married women, use their MAIDEN (birth) last name — and write each person's
name exactly the same way every time.**

The tree connects people by matching names, so a person must be referenced by the
same name they used in their own row. Example — Ana, born *Reyes*, married to Juan
Gedorio:

| Where Ana appears | What to type |
|---|---|
| Ana's own row → Last name | `Reyes` |
| Her child's row → Mother's full name | `Ana Reyes` |
| Her husband's row → Spouse's full name | `Ana Reyes` |

Never mix `Ana Reyes` and `Ana Gedorio` for the same person — the app would treat
them as two different people. (Men keep their birth surname, so no maiden/married
distinction for fathers or husbands. If a maiden name is unknown, pick one spelling
and use it everywhere.)

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

## Messages to share

**Google Form description** (paste under the form title, so the rule sits at the top):

> Fill this in for yourself, then again for any relative you want to add (parents,
> kids, spouse). Please write each person's name the same way every time, and for
> married women use their MAIDEN (birth) last name — that's how everyone links
> together correctly. Thank you! 🌳

**Group-chat message — Google Form version:**

> 👨‍👩‍👧 We're building our family tree! Tap this link and fill in your details — 2
> minutes on your phone, no app or sign-in needed. Fill it once for yourself, then
> again for anyone else you want to add. Two tips so everyone connects properly:
> ① type each person's name the same way every time, and ② for married women use
> their maiden (birth) last name. 🌳
> [paste your Google Form link here]

**Group-chat message — shared Google Sheet version:**

> 👨‍👩‍👧 Family tree time! Tap this link and add yourself (and relatives) as new rows
> at the bottom — one row per person. Please don't change other people's rows. Two
> tips: ① write each person's name the same way every time, and ② for married women
> use their maiden (birth) last name — that's how everyone links up. 🌳
> [paste your Google Sheet link here]

> **Note for the Sheet version:** keep the column-header row as the very first row —
> don't add a tip row above it, or the import won't recognize the columns. Put the
> naming tip in the chat message instead (as above).
