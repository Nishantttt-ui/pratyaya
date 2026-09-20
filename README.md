# Pratyaya — Explainable Credit Risk for Thin-File Borrowers

> *Pratyaya* (प्रत्यय), Sanskrit for trust or conviction. The English word *credit*
> comes from the Latin *credere* — to believe. Both words describe the same thing:
> a lender's belief that a borrower will repay.

Submission for the Synchrony Hackathon — **Problem Statement 2: AI-Powered
Financial Inclusion, Dynamic Risk Assessment for Underserved Segments.**

## The core design decision

**The language model sits on the explanation path, never the decision path.**

A deterministic, auditable gradient-boosted model produces every credit
decision. That decision is final before any LLM is invoked. The LLM's only job
is to turn the decision and its reason codes into language a borrower can act
on, grounded in retrieved regulatory text.

A hallucination, a provider outage, or a change of vendor can therefore alter
how a decision is *described* — never what the decision *is*.

*Status: in active development. Setup instructions and architecture diagram to follow.*
