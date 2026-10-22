import { money } from "../api.js";

export default function ProductList({ products, onPick, onRepeat, busy }) {
  if (!products?.length) return null;
  return (
    <>
    <div className="products-head">
      <h2 className="small-h">Your options</h2>
      <button type="button" className="btn btn-quiet btn-small" onClick={onRepeat} disabled={busy}>Read them again</button>
    </div>
    <ol className="products" aria-label="Options found">
      {products.map((p, i) => (
        <li key={p.id} className="product">
          {p.image ? <img src={p.image} alt="" loading="lazy" /> : <span className="product-img-empty" aria-hidden="true" />}
          <div className="product-body">
            <p className="product-title">
              <span className="product-num">Option {i + 1}.</span> {p.title}
            </p>
            <p className="product-meta">
              <strong>{money(p.price, p.currency)}</strong>
              {p.retailer ? ` at ${p.retailer}` : ""}
              {p.simulated ? " (simulated listing)" : ""}
            </p>
          </div>
          <button type="button" className="btn btn-quiet" onClick={() => onPick(i + 1, p)} disabled={busy}>
            Choose option {i + 1}
          </button>
        </li>
      ))}
    </ol>
    </>
  );
}
