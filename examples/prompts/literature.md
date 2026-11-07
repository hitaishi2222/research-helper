# Literature — {{QUESTION}}

**Question to answer:** {{QUESTION}}
**Papers land in:** `papers/` · **takes in:** `LITERATURE.md`
**Search tool:** as written in `.rh/env.json` (`literature.search`)
**Output type the user asked for:** {{OUTPUT}}

Do this, in order:

1. Search with the configured tool; download only open-access PDFs.
2. Read every paper you cite with the configured reader. Never paraphrase a paper
   you have not read, never substitute a reference.
3. For each paper that survives reading, append under its DOI in
   `LITERATURE.md`: citation, DOI, one-paragraph relevance, exactly what we take
   (method / number / parameter), what we reject and why, page anchors. Useful
   findings noticed mid-read get their own line with that DOI, even in rejected
   papers.
4. Build the pattern tally in `OUTPUT_LAYOUT.md` while reading — one row per
   paper (what to copy or avoid, equations and where they appear, figures with
   axes and units, how it explains, what it never shows). Keep **exactly one**
   layout under `## Our layout`.
5. Implementation sourcing goes in `GAPS.md`: repo/paper, licence, what we
   borrow, what upstream is missing, credit.

Paywall → report the DOI and stop; the Orchestrator asks the user for the PDF.
Absences go under "not obtained" in `LITERATURE.md`.

Exit answer: is the question already answered by existing work, or is there a
named gap we can attack?
