# Regulatory corpus — provenance and limitations

**These files are paraphrases, not legal text.**

Every provision below is a plain-language summary written for this prototype,
carrying a citation to the real instrument it summarises. None of it is verbatim
statutory or regulatory language, and none of it should be relied on for
compliance purposes.

This matters for the project's own argument. The system exists to stop a
language model from inventing authoritative-sounding text. Seeding its retrieval
corpus with invented "quotations" from RBI circulars would commit precisely the
failure the architecture is built to prevent, and the citations would not
survive a reader who knows the regulations.

For a production deployment this corpus would be replaced with the official
texts ingested from rbi.org.in and the India Code, with per-clause
identifiers and effective dates. The retrieval, chunking, embedding and
citation machinery is unchanged by that substitution — only the source of the
text differs.

## Instruments summarised

| File | Instrument |
|---|---|
| `rbi_digital_lending.md` | RBI Digital Lending Directions (originating in the Guidelines on Digital Lending, September 2022) |
| `rbi_fair_practices.md` | RBI Fair Practices Code for NBFCs (Master Direction) |
| `dpdp_act_2023.md` | Digital Personal Data Protection Act, 2023 |
| `account_aggregator.md` | RBI Master Direction, NBFC–Account Aggregator (2016) and the DEPA consent framework |
| `credit_information.md` | Credit Information Companies (Regulation) Act, 2005 and related RBI directions |
