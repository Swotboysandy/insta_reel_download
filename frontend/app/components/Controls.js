"use client";
import { useId } from "react";
import { ChevronDown, LoaderCircle, RefreshCw } from "lucide-react";
export function Button({
  children,
  primary = false,
  danger = false,
  busy = false,
  ...props
}) {
  return (
    <button
      type="button"
      className={`btn ${primary ? "btnPrimary" : danger ? "btnDanger" : "btnSecondary"}`}
      {...props}
    >
      {busy && <LoaderCircle size={16} className="spin" />}
      {children}
    </button>
  );
}
export function Field({ label, children, hint }) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {typeof children === "function" ? children(id) : children}
      {hint && <p className="hint">{hint}</p>}
    </div>
  );
}
export function Input({
  label,
  value,
  onChange,
  type = "text",
  hint,
  ...props
}) {
  return (
    <Field label={label} hint={hint}>
      {(id) => (
        <input
          id={id}
          name={id}
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete="off"
          {...props}
        />
      )}
    </Field>
  );
}
export function Section({ title, children, open = true }) {
  return (
    <details className="settingsSection" open={open}>
      <summary>
        {title}
        <ChevronDown size={16} />
      </summary>
      <div className="settingsBody">{children}</div>
    </details>
  );
}
export function Refresh({ onClick, busy }) {
  return (
    <button
      type="button"
      className="iconButton"
      aria-label="Refresh files"
      disabled={busy}
      onClick={onClick}
    >
      <RefreshCw size={17} className={busy ? "spin" : ""} />
    </button>
  );
}
export function Empty({ icon: Icon, title, children }) {
  return (
    <div className="emptyState">
      <Icon size={28} strokeWidth={1.5} />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
