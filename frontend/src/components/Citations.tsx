import type { Citation } from "../types";

export function Citations({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null;
  return (
    <div className="card">
      <h3>Your rights and the rules that apply</h3>
      {citations.map((citation) => (
        <div key={citation.chunk_id} className="citation">
          <div className="id">[{citation.chunk_id}]</div>
          <div className="heading">{citation.heading}</div>
          <div className="body">{citation.text}</div>
          <div className="source">{citation.citation}</div>
        </div>
      ))}
      <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>
        Provisions are plain-language paraphrases prepared for this prototype,
        each citing the instrument it summarises. They are not verbatim legal text.
      </p>
    </div>
  );
}
