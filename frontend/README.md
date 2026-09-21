# Pratyaya — interface

The React front end for [Pratyaya](../README.md). Two views of the same credit
decision: what an underwriter sees, and what the borrower receives.

**Live:** https://pratyaya-beta.vercel.app

## Running it

```bash
npm install
cp .env.example .env     # VITE_API_BASE defaults to http://localhost:8000
npm run dev              # http://localhost:5173
```

The API must be running — see the [project README](../README.md#setup). Sign in
with the demo accounts configured in the API's `.env`.

```bash
npm run build            # type-check and production build
```

## What is worth looking at

**[`components/Letter.tsx`](src/components/Letter.tsx)** renders the applicant's
notice. Generated prose is set as a letter, serif on paper, because that is what
it is: a formal communication about a credit decision. The deterministic notice
keeps a fixed-width document form, so a reader can tell which path produced what
they are reading without consulting the provenance block.

**[`components/Pipeline.tsx`](src/components/Pipeline.tsx)** shows how the
decision was produced, carrying only facts the response actually contains. The
deterministic stages are labelled by what they are rather than given invented
timings; the one real measurement, how long the model took, comes from the API.

**[`components/ReasonBars.tsx`](src/components/ReasonBars.tsx)** scales each bar
against the largest absolute contribution, so the visual ranking matches the
model's real attribution instead of flattening every factor to look equally
important. An applicant is never shown the signed contribution — it is a
log-odds figure they cannot audit — so that view falls back to rank order.

**[`api.ts`](src/api.ts)** holds the bearer token in module scope rather than
`localStorage`. It is short-lived and re-obtained on reload, which keeps it out
of persistent browser storage where an XSS payload could read it.

## Role projection

The same request returns different shapes depending on who asks. An applicant
response omits the probability, the threshold, the signed contributions and the
provenance entirely — the fields are absent, not nulled — while keeping the
reasons, the recourse and the citations that the RBI Fair Practices Code
requires be communicated. Signing in as each account in turn is the quickest way
to see it.
