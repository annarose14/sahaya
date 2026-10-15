export default function TalkButton({ listening, disabled, onPress }) {
  return (
    <button
      type="button"
      className={`talk ${listening ? "is-listening" : ""}`}
      onClick={onPress}
      disabled={disabled}
      aria-pressed={listening}
      aria-label={listening ? "Listening. Press to stop." : "Press to talk"}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true" width="40" height="40">
        <rect x="9" y="3" width="6" height="11" rx="3" fill="currentColor" />
        <path d="M5 11a7 7 0 0 0 14 0M12 18v3" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" />
      </svg>
    </button>
  );
}
