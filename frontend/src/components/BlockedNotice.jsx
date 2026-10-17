import { money } from "../api.js";

// Shown when a search result contained hidden instructions aimed at the AI. Those listings are never offered.
export default function BlockedNotice({ items }) {
  if (!items?.length) return null;
  return (
    <section className="blocked" aria-live="polite" aria-labelledby="blocked-h">
      <h2 id="blocked-h">
        {items.length === 1 ? "I left out 1 listing" : `I left out ${items.length} listings`} that tried to trick me
      </h2>
      <ul>
        {items.map((it, i) => (
          <li key={i}>
            <span className="blocked-title">{it.title}</span>
            <span className="blocked-meta">
              {money(it.price, it.currency)}{it.shop ? ` at ${it.shop}` : ""}. It said: “{it.found?.[0]}”
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
