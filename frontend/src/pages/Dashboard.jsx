import { useCallback, useEffect, useMemo, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ModuleRegistry, themeQuartz } from "ag-grid-community";
import { api, money } from "../api.js";

ModuleRegistry.registerModules([AllCommunityModule]);

// AG Grid themed with Sahaya's own colours, so it follows light and dark mode.
const theme = themeQuartz.withParams({
  fontFamily: "inherit",
  fontSize: 16,
  headerFontSize: 15,
  headerFontWeight: 700,
  backgroundColor: "var(--surface)",
  foregroundColor: "var(--ink)",
  headerBackgroundColor: "var(--bg)",
  borderColor: "var(--line)",
  accentColor: "var(--focus)",
  rowHoverColor: "color-mix(in srgb, var(--marigold) 10%, transparent)",
  wrapperBorderRadius: 18,
  rowVerticalPaddingScale: 1.4,
  spacing: 9,
});

const TONE = { paid: "ok", refunded: "info", awaiting_family: "warn", awaiting_confirm: "wait",
  awaiting_paypal: "wait", blocked: "stop", declined: "stop", cancelled: "muted" };

function StatusPill({ data }) {
  return <span className={`pill pill-${TONE[data.status] || "muted"}`}>{data.status_label}</span>;
}

function PayPalCell({ data }) {
  if (data.paypal_check === "none") return <span className="muted-cell">No payment made</span>;
  if (data.paypal_check === "unavailable") return <span className="muted-cell">PayPal didn't answer</span>;
  const agree = data.matches_paypal;
  return (
    <span className="pp-cell">
      <span className={agree === false ? "pp-bad" : "pp-ok"}>
        <span aria-hidden="true">{agree === false ? "⚠ " : "✓ "}</span>
        {agree === false ? `PayPal says ${data.paypal_label}` : data.paypal_label}
      </span>
      <span className="pp-id">{data.paypal_capture_id || data.paypal_order_id}</span>
    </span>
  );
}

function ItemCell({ data }) {
  return (
    <span className="item-cell">
      <span className="item-title">{data.quantity > 1 ? `${data.quantity} × ` : ""}{data.item}</span>
      {data.shop && <span className="item-shop">at {data.shop}</span>}
    </span>
  );
}

// On phones one rich column reads better than a table you have to scroll sideways.
function PhoneCell({ data }) {
  return (
    <span className="phone-cell">
      <span className="phone-top">
        <StatusPill data={data} />
        <strong>{money(data.total, data.currency)}</strong>
      </span>
      <ItemCell data={data} />
      {data.reason && <span className="item-why">{data.reason}</span>}
      <PayPalCell data={data} />
    </span>
  );
}

function useNarrow() {
  const [narrow, setNarrow] = useState(() => window.innerWidth < 760);
  useEffect(() => {
    const on = () => setNarrow(window.innerWidth < 760);
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return narrow;
}

const SUGGESTIONS = ["Did anything unusual happen today?", "How much was spent today?", "What did Sahaya stop, and why?"];

export default function Dashboard() {
  const sid = new URLSearchParams(window.location.search).get("sid");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [asking, setAsking] = useState(false);
  const narrow = useNarrow();

  const load = useCallback(() => {
    if (!sid) { setError("This link is missing whose dashboard to show."); return; }
    api.dashboard(sid).then((d) => { setData(d); setError(""); }).catch((e) => setError(e.message));
  }, [sid]);

  useEffect(() => {
    load();
    const id = setInterval(load, 15000); // keep it live while the family member watches
    return () => clearInterval(id);
  }, [load]);

  async function ask(q) {
    const text = (q ?? question).trim();
    if (text.length < 2 || asking) return;
    setQuestion(text);
    setAsking(true);
    setAnswer("");
    try { setAnswer((await api.ask(sid, text)).answer); } catch (e) { setAnswer(e.message); } finally { setAsking(false); }
  }

  const columns = useMemo(() => (narrow ? [
    { headerName: "Purchases, newest first", field: "created", sort: "desc", flex: 1, autoHeight: true,
      cellRenderer: PhoneCell, getQuickFilterText: (p) => `${p.data.item} ${p.data.status_label} ${p.data.shop}` },
  ] : [
    { headerName: "When", field: "created", sort: "desc", width: 145,
      valueFormatter: (p) => new Date(p.value * 1000).toLocaleString("en-AU", { weekday: "short", hour: "numeric", minute: "2-digit" }) },
    { headerName: "Item", field: "item", flex: 2, minWidth: 220, autoHeight: true, cellRenderer: ItemCell,
      getQuickFilterText: (p) => `${p.data.item} ${p.data.shop}` },
    { headerName: "Total", field: "total", width: 140, type: "rightAligned",
      valueFormatter: (p) => money(p.value, p.data.currency) },
    { headerName: "Status", field: "status_label", width: 205, cellRenderer: StatusPill },
    { headerName: "Why", field: "reason", flex: 1.4, minWidth: 200, wrapText: true, autoHeight: true,
      valueFormatter: (p) => p.value || (p.data.status === "paid" ? `All ${p.data.checks_total} checks passed` : "") },
    { headerName: "Checked with PayPal", field: "paypal_label", width: 220, cellRenderer: PayPalCell, autoHeight: true },
  ]), [narrow]);

  const s = data?.summary;
  const pct = s ? Math.min(100, Math.round((s.spent_today / s.daily_cap) * 100)) : 0;

  return (
    <div className="shell wide">
      <header className="top">
        <p className="brand"><span className="brand-dot" aria-hidden="true" />Sahaya</p>
        <a className="toplink" href="/">Open Sahaya</a>
      </header>
      <main>
        <h1 className="page-h">Family dashboard</h1>
        <p className="muted">Everything Sahaya did for your relative. Each payment is checked live with PayPal.</p>
        {error && <p className="notice notice-stop" role="alert">{error}</p>}

        {s && (
          <section className="tiles" aria-label="Today at a glance">
            <div className="tile tile-wide">
              <p className="tile-label">Spent today</p>
              <p className="tile-num">{money(s.spent_today)} <span className="tile-of">of {money(s.daily_cap)}</span></p>
              <div className="meter" role="meter" aria-valuemin={0} aria-valuemax={s.daily_cap} aria-valuenow={s.spent_today}
                aria-label={`Spent ${money(s.spent_today)} of the ${money(s.daily_cap)} daily limit`}>
                <span style={{ width: `${pct}%` }} className={pct >= 80 ? "meter-hot" : ""} />
              </div>
            </div>
            <div className="tile">
              <p className="tile-label">Waiting for you</p>
              <p className={`tile-num ${s.waiting_for_you ? "tile-attn" : ""}`}>{s.waiting_for_you}</p>
            </div>
            <div className="tile">
              <p className="tile-label">Stopped by Sahaya</p>
              <p className="tile-num">{s.stopped_count + s.tricks_caught}</p>
              <p className="tile-sub">{s.tricks_caught} trick listing{s.tricks_caught === 1 ? "" : "s"}</p>
            </div>
            <div className="tile">
              <p className="tile-label">Refunded</p>
              <p className="tile-num">{money(s.refunded_total)}</p>
            </div>
          </section>
        )}

        {s?.paypal_mismatches > 0 && (
          <p className="notice notice-stop" role="alert">
            {s.paypal_mismatches} purchase{s.paypal_mismatches === 1 ? " doesn't" : "s don't"} match what PayPal says. Check the rows marked ⚠.
          </p>
        )}

        <section className="ask" aria-labelledby="ask-h">
          <h2 id="ask-h" className="small-h">Ask about these purchases</h2>
          <form className="composer-row" onSubmit={(e) => { e.preventDefault(); ask(); }}>
            <label htmlFor="ask-q" className="sr-only">Your question</label>
            <input id="ask-q" value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={300}
              placeholder="Did Mum buy anything unusual today?" autoComplete="off" />
            <button className="btn btn-dark" type="submit" disabled={asking || question.trim().length < 2}>Ask</button>
          </form>
          <div className="chips">
            {SUGGESTIONS.map((q) => (
              <button key={q} type="button" className="chip" onClick={() => ask(q)} disabled={asking}>{q}</button>
            ))}
          </div>
          <p className="answer" aria-live="polite">{asking ? "Looking through the purchases…" : answer}</p>
        </section>

        <section aria-labelledby="hist-h">
          <div className="grid-head">
            <h2 id="hist-h" className="small-h">Purchases</h2>
            <label className="grid-search">
              <span className="sr-only">Search purchases</span>
              <input type="search" placeholder="Search" value={filter} onChange={(e) => setFilter(e.target.value)} />
            </label>
          </div>
          <div className="grid-wrap">
            <AgGridReact
              theme={theme}
              rowData={data?.rows || []}
              columnDefs={columns}
              defaultColDef={{ sortable: true, resizable: true, filter: false }}
              quickFilterText={filter}
              getRowId={(p) => p.data.id}
              domLayout="autoHeight"
              overlayNoRowsTemplate="<span>No purchases yet.</span>"
              ensureDomOrder
              suppressCellFocus={false}
            />
          </div>
          {data && (
            <p className="muted small">
              Checked with PayPal at {new Date(data.checked_at * 1000).toLocaleTimeString("en-AU", { hour: "numeric", minute: "2-digit" })}.
              Updates every 15 seconds.
            </p>
          )}
        </section>

        {data?.tricks?.length > 0 && (
          <section className="blocked" aria-labelledby="tricks-h">
            <h2 id="tricks-h">Listings that tried to trick Sahaya</h2>
            <ul>
              {data.tricks.map((t, i) => (
                <li key={i}>
                  <span className="blocked-title">{t.title}</span>
                  <span className="blocked-meta">While searching “{t.query}”. It said: “{t.found}”. Never shown, never bought.</span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </main>
    </div>
  );
}
