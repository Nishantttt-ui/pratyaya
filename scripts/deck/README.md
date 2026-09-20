# Deck generator

Regenerates `docs/Pratyaya-Synchrony-Hackathon.pptx` from source, so the deck
stays consistent with the numbers in `ml/artifacts/metrics.json` and
`eval/reports/evaluation.json` rather than drifting from them.

```bash
npm install pptxgenjs
node scripts/deck/build_deck.js
```

The figures quoted in the slides come from those two reports. If the model is
retrained, update them here so the deck and the repository do not disagree.
