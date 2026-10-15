import { useEffect, useState } from "react";
import { api, money } from "../api.js";
import { speak } from "../speech.js";

export default function Done() {
  const q = new URLSearchParams(window.location.search);
  const pid = q.get("pid");
  const result = q.get("result");
  const [p, setP] = useState(null);

  useEffect(() => {
    if (pid) api.purchase(pid).then(setP).catch(() => {});
  }, [pid]);

  const text =
    result === "paid" && p
      ? `Paid. ${money(p.total, p.currency)} for ${p.product.title}. You can ask me about this order or a refund any time.`
      : result === "cancelled"
        ? "You cancelled in PayPal. Nothing was paid."
        : result === "error"
          ? "PayPal couldn't finish the payment. Nothing was taken."
          : "";

  useEffect(() => { if (text) speak(text); }, [text]);

  return (
    <div className="shell narrow">
      <header className="top"><p className="brand"><span className="brand-dot" aria-hidden="true" />Sahaya</p></header>
      <main>
        <h1 className={`page-h ${result === "paid" ? "ok-text" : ""}`}>
          {result === "paid" ? "Payment complete" : result === "cancelled" ? "Payment cancelled" : "Payment not completed"}
        </h1>
        <p className="lead" aria-live="polite">{text}</p>
        <a className="btn btn-dark" href="/">Back to Sahaya</a>
      </main>
    </div>
  );
}
