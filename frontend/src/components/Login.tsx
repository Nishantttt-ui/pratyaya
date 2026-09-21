import { useState } from "react";
import { signIn } from "../api";

export function Login({ onSignedIn }: { onSignedIn: (role: string) => void }) {
  const [username, setUsername] = useState("underwriter");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onSignedIn(await signIn(username, password));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <div className="card">
        <div className="brand">Pratyaya</div>
        <p className="muted" style={{ marginTop: 6, marginBottom: 22, fontSize: 14 }}>
          Explainable credit assessment for thin-file borrowers. Sign in as an
          underwriter to see the full decision, or as an applicant to see the view a
          borrower receives.
        </p>
        <form onSubmit={submit}>
          <label htmlFor="u">Username</label>
          <input id="u" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          <label htmlFor="p">Password</label>
          <input id="p" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
          {error && <div className="error" style={{ marginBottom: 14 }}>{error}</div>}
          <button className="btn primary" style={{ width: "100%" }} disabled={busy || !password}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <div className="hint">
          Demo accounts: <code>underwriter</code> and <code>applicant</code>. Passwords
          are set in <code>.env</code>; if left unset, a random one is generated per run
          and printed once to the server console.
        </div>
      </div>
    </div>
  );
}
