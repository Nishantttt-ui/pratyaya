import type { Citation } from "../types";

export function Citations({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null;
  return (
    <div className="card">
      <h3>Your rights and the rules that apply</h3>
      {citations.map((c) => (
        <div key={c.chunk_id} className="citation">
          <div className="head">
            <span className="id">{c.chunk_id}</span>
            <span className="heading">{c.heading}</span>
          </div>
          <div className="body">{c.text}</div>
          <div className="source">{c.citation}</div>
        </div>
      ))}
      <p className="muted" style={{ fontSize: 12, marginBottom: 0, marginTop: 12 }}>
        Provisions are plain-language paraphrases prepared for this prototype, each
        citing the instrument it summarises. They are not verbatim legal text.
      </p>
    </div>
  );
}
