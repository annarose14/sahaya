import { useCallback, useEffect, useRef, useState } from "react";
import { api, money, sessionId } from "./api.js";
import { canListen, listen, speak, stopSpeaking } from "./speech.js";
import TalkButton from "./components/TalkButton.jsx";
import ProductList from "./components/ProductList.jsx";
import PurchasePanel from "./components/PurchasePanel.jsx";
import Trace from "./components/Trace.jsx";
import BlockedNotice from "./components/BlockedNotice.jsx";

const GREETING =
  "Hello, I'm Sahaya. Tell me what you'd like to buy, and I'll find a few options and read them to you. I never pay without your yes.";

export default function App() {
  const sid = useRef(sessionId()).current;
  const [messages, setMessages] = useState([{ role: "assistant", text: GREETING }]);
  const [products, setProducts] = useState(null);
  const [purchase, setPurchase] = useState(null);
  const [trace, setTrace] = useState([]);
  const [rules, setRules] = useState(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [voiceOn, setVoiceOn] = useState(true);
  const [server, setServer] = useState("checking"); // checking | waking | up | down
  const [ignored, setIgnored] = useState([]);
  const [safetyDemo, setSafetyDemo] = useState(false);
  const recRef = useRef(null);
  const endRef = useRef(null);

  const say = useCallback((text) => {
    setMessages((m) => [...m, { role: "assistant", text }]);
    if (voiceOn) speak(text);
  }, [voiceOn]);

  const refreshTrace = useCallback(() => api.trace(sid).then(setTrace).catch(() => {}), [sid]);

  // The free server sleeps when nobody uses it. Waking takes up to a minute, so say so instead of looking broken.
  const connect = useCallback(async () => {
    setServer("checking");
    const slow = setTimeout(() => setServer((s) => (s === "checking" ? "waking" : s)), 2500);
    const started = Date.now();
    while (Date.now() - started < 120000) {
      try {
        const h = await api.health();
        clearTimeout(slow);
        setRules(h.rules);
        setServer("up");
        // Coming back from PayPal: show the latest order again.
        api.purchases(sid).then((list) => { if (list[0] && list[0].status !== "cancelled") setPurchase(list[0]); }).catch(() => {});
        refreshTrace();
        return;
      } catch {
        await new Promise((r) => setTimeout(r, 4000));
      }
    }
    clearTimeout(slow);
    setServer("down");
  }, [sid, refreshTrace]);

  useEffect(() => { connect(); }, [connect]);

  // Scroll to new content only after the conversation starts, so keyboard users begin at the top
  // (scrolling on load moved Chrome's Tab starting point past the skip link).
  useEffect(() => {
    if (messages.length > 1) endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, purchase]);

  // While a trusted contact decides, check back every few seconds.
  useEffect(() => {
    if (purchase?.status !== "awaiting_family") return;
    const id = setInterval(async () => {
      const p = await api.purchase(purchase.id).catch(() => null);
      if (!p || p.status === "awaiting_family") return;
      setPurchase(p);
      refreshTrace();
      if (p.status === "awaiting_confirm") say(`Your trusted contact approved it. The total is ${money(p.total, p.currency)}. Say yes to pay with PayPal, or no to cancel.`);
      if (p.status === "declined") say("Your trusted contact said no, so I won't buy it.");
    }, 3000);
    return () => clearInterval(id);
  }, [purchase, refreshTrace, say]);

  async function confirm() {
    setBusy(true);
    try {
      const p = await api.confirm(purchase.id);
      setPurchase(p);
      refreshTrace();
      if (p.status === "awaiting_paypal" && p.approve_url) {
        say("Opening PayPal so you can approve the payment.");
        setTimeout(() => { window.location.href = p.approve_url; }, 1800);
      } else if (p.status === "blocked") {
        say(p.decision.reasons.join(" "));
      }
    } catch (e) {
      say(`PayPal didn't accept that. ${e.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    setBusy(true);
    try {
      setPurchase(await api.cancel(purchase.id));
      say("Okay, I've cancelled it. Nothing was paid.");
      refreshTrace();
    } catch (e) { say(e.message); } finally { setBusy(false); }
  }

  async function refund() {
    setBusy(true);
    try {
      setPurchase(await api.refund(purchase.id));
      say("Done. PayPal is refunding your money.");
      refreshTrace();
    } catch (e) { say(e.message); } finally { setBusy(false); }
  }

  async function send(text) {
    const clean = text.trim();
    if (!clean || busy) return;
    setDraft("");
    stopSpeaking();
    setMessages((m) => [...m, { role: "user", text: clean }]);

    // A plain yes or no to a pending payment is decided by the server's plain code, never by the AI.
    setBusy(true);
    try {
      const res = await api.chat(sid, clean);
      if (res.products) setProducts(res.products);
      if (res.products) setIgnored(res.ignored || []);
      if (res.purchase) setPurchase(res.purchase);
      say(res.reply);
      const p = res.purchase;
      if (p?.status === "awaiting_paypal" && p.approve_url && purchase?.status !== "awaiting_paypal") {
        setTimeout(() => { window.location.href = p.approve_url; }, 2200);
      }
    } catch (e) {
      say(`Something went wrong on my side. ${e.message}`);
    } finally {
      setBusy(false);
      refreshTrace();
    }
  }

  function toggleListen() {
    if (listening) { recRef.current?.stop(); return; }
    stopSpeaking();
    setListening(true);
    recRef.current = listen({
      onText: (t) => send(t),
      onEnd: () => setListening(false),
      onError: (err) => {
        setListening(false);
        if (err === "not-allowed" || err === "service-not-allowed") {
          say("The microphone is blocked. Allow it from the icon in the address bar, or type instead.");
        } else if (err === "no-speech") {
          say("I didn't hear anything. Press the button and try again.");
        } else if (err === "network") {
          say("Voice input needs an internet connection. You can type instead.");
        }
      },
    });
  }

  // Space bar talks, unless you're typing.
  useEffect(() => {
    const onKey = (e) => {
      if (e.code !== "Space" || e.repeat) return;
      const tag = document.activeElement?.tagName;
      if (["INPUT", "TEXTAREA", "BUTTON", "A", "SUMMARY"].includes(tag)) return;
      e.preventDefault();
      if (canListen && server === "up") toggleListen();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");

  return (
    <div className="shell">
      <a className="skip" href="#composer">Skip to talk</a>
      <header className="top">
        <p className="brand"><span className="brand-dot" aria-hidden="true" />Sahaya</p>
        <a className="toplink" href={`/dashboard?sid=${sid}`} target="_blank" rel="noreferrer">Family dashboard</a>
        <label className="switch">
          <input type="checkbox" checked={voiceOn} onChange={(e) => { setVoiceOn(e.target.checked); stopSpeaking(); }} />
          Read replies aloud
        </label>
      </header>

      <main>
        <h1 className="sr-only">Sahaya shopping helper</h1>
        {server === "waking" && (
          <p className="notice" role="status">
            Waking up Sahaya. This takes up to a minute the first time, then it's quick.
          </p>
        )}
        {server === "down" && (
          <p className="notice notice-stop" role="alert">
            Sahaya's server isn't answering.{" "}
            <button type="button" className="linkish" onClick={connect}>Try again</button>
          </p>
        )}
        <p className="lead" aria-live="polite">{lastAssistant?.text}</p>

        {rules && (
          <p className="rules">
            Your limits: {money(rules.daily_spend_cap)} a day. Anything over {money(rules.family_approval_over)} goes to your trusted contact first.
          </p>
        )}

        <BlockedNotice items={ignored} />
        <ProductList products={products} onPick={(n) => send(`Option ${n}`)} />
        <PurchasePanel purchase={purchase} busy={busy} onConfirm={confirm} onCancel={cancel} onRefund={refund} />

        <details className="history">
          <summary>Conversation ({messages.length})</summary>
          <ol>
            {messages.map((m, i) => (
              <li key={i} className={`msg msg-${m.role}`}>
                <span className="msg-who">{m.role === "user" ? "You" : "Sahaya"}</span>
                {m.text}
              </li>
            ))}
          </ol>
        </details>
        <Trace items={trace} />
        <details className="demo">
          <summary>Safety demo for judges</summary>
          <label className="switch">
            <input
              type="checkbox"
              checked={safetyDemo}
              onChange={async (e) => {
                const on = e.target.checked;
                setSafetyDemo(on);
                await api.safetyDemo(sid, on).catch(() => setSafetyDemo(!on));
              }}
            />
            Add a fake listing to my next searches that tries to trick the AI into buying
          </label>
        </details>
        <div ref={endRef} />
      </main>

      <form id="composer" tabIndex={-1} className="composer" onSubmit={(e) => { e.preventDefault(); send(draft); }}>
        <TalkButton listening={listening} disabled={busy || !canListen || server !== "up"} onPress={toggleListen} />
        <div className="composer-field">
          <label htmlFor="say" className="composer-label">
            {server !== "up" ? "Connecting to Sahaya…" : busy ? "Sahaya is working…" : listening ? "Listening…"
              : canListen ? "Press the button or space bar to talk, or type" : "Type what you'd like (voice needs Chrome, Edge or Safari)"}
          </label>
          <div className="composer-row">
            <input id="say" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="A kettle I can use without looking" autoComplete="off" maxLength={2000} disabled={busy} />
            <button type="submit" className="btn btn-dark" disabled={busy || !draft.trim() || server !== "up"}>Send</button>
          </div>
        </div>
      </form>
    </div>
  );
}
