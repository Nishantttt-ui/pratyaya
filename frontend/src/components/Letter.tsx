import type { ReactNode } from "react";

/**
 * Renders the applicant's notice.
 *
 * Two shapes arrive here and they are deliberately not styled alike. Generated
 * prose is set as a letter — serif, on paper — because that is what it is: a
 * formal communication about a credit decision. The deterministic notice is a
 * fixed-width document and is set in mono, so a reader can tell at a glance
 * which path produced what they are reading without consulting the provenance.
 */
function withCitations(text: string): ReactNode[] {
  // Provision ids look like [FPC-01]; lift them out so they read as references
  // rather than as punctuation in the middle of a sentence.
  return text.split(/(\[[A-Z]{2,5}-\d{2}\])/g).map((part, i) =>
    /^\[[A-Z]{2,5}-\d{2}\]$/.test(part)
      ? <span key={i} className="cite">{part.slice(1, -1)}</span>
      : <span key={i}>{part}</span>
  );
}

export function Letter({ text }: { text: string }) {
  const isDeterministic = text.trimStart().startsWith("KEY FACTS");
  if (isDeterministic) return <div className="letter plain">{text}</div>;

  return (
    <div className="letter">
      {text.split(/\n\s*\n/).filter((p) => p.trim()).map((para, i) => (
        <p key={i}>{withCitations(para.trim())}</p>
      ))}
    </div>
  );
}
