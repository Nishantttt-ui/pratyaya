import { useEffect, useRef, useState } from "react";
import { assess, currentRole, fetchHealth, fetchSample, signOut } from "./api";
import type { Applicant, Assessment } from "./types";
import { ApplicantList } from "./components/ApplicantList";
import { DecisionPanel } from "./components/DecisionPanel";
import { Login } from "./components/Login";

export default function App() {
  const [role, setRole] = useState<string | null>(null);
  const [applicants, setApplicants] = useState<Applicant[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [result, setResult] = useState<Assessment | null>(null);
  const [ntcOnly, setNtcOnly] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  async function loadSample(newToCreditOnly: boolean) {
    setError(null);
    try {
      setApplicants(await fetchSample(8, newToCreditOnly));
      setSelected(null);
      setResult(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load applicants");
    }
  }

  useEffect(() => {
    if (!role) return;
    loadSample(ntcOnly);
    fetchHealth().then((h) => setHealth(h.components)).catch(() => undefined);
  }, [role]);

  async function runAssessment(index: number) {
    setSelected(index);
    setBusy(true);
    setError(null);
    try {
      setResult(await assess(applicants[index]));
      // Below 900px the two columns stack, so the decision lands under the
      // applicant list and off-screen. Bring it into view, otherwise a click
      // looks like it did nothing.
      if (window.matchMedia("(max-width: 900px)").matches) {
        requestAnimationFrame(() =>
          resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Assessment failed");
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  if (!role) return <Login onSignedIn={setRole} />;

  return (
    <div className="app">
      <header className="masthead">
        <span className="wordmark">Pratyaya</span>
        <span className="tagline">explainable credit for thin-file borrowers</span>
        <span className="spacer" />
        {health && (
          <span className="chip" title="retrieval backend in use">
            {String(health.policy_corpus)} provisions · {String(health.vector_store)}
          </span>
        )}
        <span className="chip accent">{currentRole()}</span>
        <button className="btn small" onClick={() => { signOut(); setRole(null); setResult(null); }}>
          Sign out
        </button>
      </header>

      <div className="layout">
        <div>
          <div className="card">
            <h3>Applicants</h3>
            <div className="row" style={{ marginBottom: 12 }}>
              <label className="row" style={{ gap: 6, fontSize: 13.5 }}>
                <input
                  type="checkbox"
                  checked={ntcOnly}
                  onChange={(e) => { setNtcOnly(e.target.checked); loadSample(e.target.checked); }}
                />
                new-to-credit only
              </label>
              <span className="spacer" />
              <button className="btn small" onClick={() => loadSample(ntcOnly)}>Shuffle</button>
            </div>
            <div className="applicant-list">
              <ApplicantList applicants={applicants} selected={selected} onSelect={runAssessment} />
            </div>
          </div>
        </div>

        <div ref={resultRef}>
          {error && <div className="error" style={{ marginBottom: 16 }}>{error}</div>}
          {busy && (
            <div className="card">
              <h3>Assessing</h3>
              <p className="muted" style={{ marginTop: -6, marginBottom: 18, fontSize: 13.5 }}>
                Scoring, decomposing the score into reason codes, searching for
                recourse, retrieving the governing provisions, and writing the notice.
              </p>
              <div className="skeleton">
                <div className="line" style={{ width: "42%", height: 26 }} />
                <div className="line" style={{ width: "100%" }} />
                <div className="line" style={{ width: "94%" }} />
                <div className="line" style={{ width: "88%" }} />
                <div className="line" style={{ width: "60%" }} />
              </div>
            </div>
          )}
          {!busy && !result && !error && (
            <div className="card empty">
              <h3>Select an applicant</h3>
              <p>
                You will see the decision, the factors that drove it in the order the
                model actually weighted them, what would change the outcome, and the
                regulatory provisions that govern it — each retrieved for this
                decision rather than boilerplate.
              </p>
            </div>
          )}
          {!busy && result && <DecisionPanel result={result} />}
        </div>
      </div>
    </div>
  );
}
