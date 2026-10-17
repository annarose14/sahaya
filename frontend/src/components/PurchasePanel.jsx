import { money } from "../api.js";

const HEADINGS = {
  awaiting_confirm: "Ready to pay",
  awaiting_family: "Waiting for your trusted contact",
  awaiting_paypal: "Finish in PayPal",
  blocked: "Sahaya stopped this purchase",
  declined: "Your trusted contact said no",
  cancelled: "Cancelled",
  paid: "Paid",
  refunded: "Refunded",
};

const CHECK_NAMES = {
  price_known: "Price confirmed",
  currency: "A currency PayPal can charge safely",
  quantity: "Sensible quantity",
  listing_safe: "Listing has no hidden instructions",
  daily_cap: "Within your daily limit",
  fair_price: "Fair price compared with other shops",
  family_threshold: "Under the amount that needs approval",
};

export default function PurchasePanel({ purchase, busy, onConfirm, onCancel, onRefund }) {
  if (!purchase) return null;
  const { status, product, quantity, total, currency, decision } = purchase;
  const tone = status === "blocked" || status === "declined" ? "stop" : status === "paid" ? "ok" : "";

  return (
    <section className={`panel ${tone}`} aria-labelledby="panel-h" aria-live="polite">
      <h2 id="panel-h">{HEADINGS[status] || status}</h2>
      <p className="panel-item">
        {quantity} × {product.title}
      </p>
      <p className="panel-total">{money(total, currency)}</p>

      {decision?.reasons?.length > 0 && (
        <ul className="reasons">
          {decision.reasons.map((r) => <li key={r}>{r}</li>)}
        </ul>
      )}

      <div className="actions">
        {status === "awaiting_confirm" && (
          <>
            <button type="button" className="btn btn-pay" onClick={onConfirm} disabled={busy}>
              Pay {money(total, currency)} with PayPal
            </button>
            <button type="button" className="btn btn-quiet" onClick={onCancel} disabled={busy}>Cancel</button>
          </>
        )}
        {status === "awaiting_paypal" && purchase.approve_url && (
          <a className="btn btn-pay" href={purchase.approve_url}>Continue to PayPal</a>
        )}
        {status === "awaiting_family" && (
          <>
            <a className="btn btn-quiet" href={`/family?pid=${purchase.id}`} target="_blank" rel="noreferrer">
              Open trusted contact view
            </a>
            <button type="button" className="btn btn-quiet" onClick={onCancel} disabled={busy}>Cancel</button>
          </>
        )}
        {status === "paid" && (
          <button type="button" className="btn btn-quiet" onClick={onRefund} disabled={busy}>Ask for a refund</button>
        )}
      </div>

      {decision?.checks?.length > 0 && (
        <details className="checks">
          <summary>What Sahaya checked before paying</summary>
          <ul>
            {decision.checks.map((c) => (
              <li key={c.check} className={c.passed ? "pass" : "fail"}>
                <span aria-hidden="true">{c.passed ? "✓" : "✕"}</span>
                <span className="sr-only">{c.passed ? "Passed: " : "Failed: "}</span>
                {CHECK_NAMES[c.check] || c.check}
                <span className="check-detail">{c.detail}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
