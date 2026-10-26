# Project template (empty inputs)

Copy this folder to `projects/<your_project>/` and fill it in.

## Folder layout

```
inputs/texts/<person_id>.md   one anonymized text per person (empty here)
inputs/persons.csv            one row per person (header only here)
templates/                    prompt parts and their SHA-256 record
config.yaml                   (optional) project settings merged over config/demo.yaml
```

## Texts

- One Markdown file per person, named `<person_id>.md`. The text used is everything from the **first `## ` heading** onward.
  Front matter or a leading `# ` title line is ignored.
- Each `## ` section is treated as one *episode*. The `C3-mixed` condition replaces a person's episodes one by one with episodes of other persons, so a text needs at least one `## ` section, and the pool of other persons' episodes must be large enough.
  A leading number in a heading, such as `## （3）...`, is renumbered in the replaced text.

## Anonymization (checklist)

- Replace person names and company names with neutral labels (for example "経営者X", "A社"); the persona block in `templates/persona_block.md` says the text is an anonymized version.
- Remove other identifying details (places, dates, products, events) that would let a model or a reader identify the person.
- Check that an automatic scan finds no names: `DEMO_NAME_LIST=<path to your own name list> python tools/check_forbidden.py` (keep the name list **outside** the repository).

## Rights

- Use only texts you are allowed to put into a model and, if you publish the repository, to publish. Published biographies and similar works are usually protected by copyright; check the rights holder's terms before using or sharing them.
- Do not commit real texts or real person tables to a public repository unless you have the right to.

## Person table (`inputs/persons.csv`)

- Required column: `person_id` (unique; it must match the text file name).
- The demo uses the columns `person_id, crisis, tech_background, crisis_source, tech_source, note` (`crisis` and `tech_background` as 1/0; `*_source` for the basis of the value; `note`). You may use other attribute columns; every column is copied to table B (`dataset_B.csv`).
- The order of rows defines the order for the `C3W` shift and for the `C3-mixed` tie-breaking.

## Templates

`templates/` holds the Japanese prompt parts (`instruction_header.md`, `persona_block.md`, `scenario_*.md`, `questions.md`, `output_format.md`, `coding_prompt.md`) and `generation_params.yaml`.
`frozen_hashes.csv` lists the SHA-256 of each file. These are hashes of the files in this repository, not the values of this study's own record of fixed files.
If you edit a file, recompute its hash and update `frozen_hashes.csv` on purpose; the build refuses to run otherwise.
`coding_prompt.md` holds the classification prompts as blocks separated by lines of `---`; their names and the answer fields they read are listed in `coding.blocks` of the config.
The `{AUTOBIOGRAPHY}` and `{INPUT_TEXT}` placeholders are set in the config (`placeholders`).
`reference_translation_en/` may hold English reference translations; they are not used for generation and not hashed.
The codebook is not included (to be added separately).
