import type { ButtonHTMLAttributes } from "react";

const BASE = "rounded-[7px] border px-3 py-1.5 text-[13px] font-medium disabled:cursor-wait disabled:opacity-60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]";
const PRIMARY = "border-[var(--text-primary)] bg-[var(--text-primary)] text-[var(--surface-1)] hover:bg-[#2b2925]";
const PLAIN = "border-[var(--border)] bg-[var(--surface-1)] hover:bg-[var(--surface-2)]";

/** The dispatch page's button: dark for the one action a person is asked for, plain for the rest. */
export default function Button({ primary, className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { primary?: boolean }) {
  return <button type="button" {...props} className={`${BASE} ${primary ? PRIMARY : PLAIN} ${className}`} />;
}
