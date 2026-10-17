import { useEffect, useState } from "react";
import { api, money } from "../api.js";

export default function Family() {
  const pid = new URLSearchParams(window.location.search).get("pid");
  const [p, setP] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!pid) { setError("This link is missing its purchase."); return; }
    api.purchase(pid).then(setP).catch((e) => setError(e.message));
  }, [pid]);

  async function decide(approve) {
    setBusy(true);
    try { setP(await api.family(pid, approve)); } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  return (
    <div className="shell narrow">
      <header className="top"><p className="brand"><span className="brand-dot" aria-hidden="true" />Sahaya</p></header>
      <main>
        <h1 className="page-h">A purchase needs your approval</h1>
        {error && <p className="panel stop" role="alert">{error}</p>}
        {p && (
          <section className="panel" aria-live="polite">
            <p className="panel-item">{p.quantity} × {p.product.title}</p>
            <p className="panel-total">{money(p.total, p.currency)}</p>
            {p.product.retailer && <p className="muted">From {p.product.retailer}</p>}
            {p.decision.reasons.length > 0 && (
              <>
                <h2 className="small-h">Why you were asked</h2>
                <ul className="reasons">{p.decision.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
              </>
            )}
            {p.status === "awaiting_family" ? (
              <div className="actions">
                <button className="btn btn-pay" onClick={() => decide(true)} disabled={busy}>Approve</button>
                <button className="btn btn-quiet" onClick={() => decide(false)} disabled={busy}>Decline</button>
              </div>
            ) : (
              <p className="done-note">
                {p.status === "declined" ? "Declined. Nothing will be paid." : "Approved. They'll be asked to confirm and pay with PayPal."}
              </p>
            )}
            <p className="muted small"><a href={`/dashboard?sid=${p.session_id}`}>See all their purchases</a></p>
          </section>
        )}
      </main>
    </div>
  );
}
