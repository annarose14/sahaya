const LABEL = { user: "You", search: "Search", tool: "Tool", policy: "Safety rules", family: "Trusted contact",
  paypal: "PayPal", cancel: "Cancelled", reply: "Sahaya", present: "Shown to you", blocked: "Blocked listing",
  answer: "Your answer", demo: "Safety demo", retry: "Retried", error: "Problem" };

export default function Trace({ items }) {
  if (!items?.length) return null;
  return (
    <details className="trace">
      <summary>Activity log ({items.length})</summary>
      <ol>
        {items.slice().reverse().map((t, i) => (
          <li key={`${t.t}-${i}`}>
            <span className="trace-step">{LABEL[t.step] || t.step}</span>
            <span className="trace-detail">{t.detail}</span>
          </li>
        ))}
      </ol>
    </details>
  );
}
