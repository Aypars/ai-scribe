import type { ReactNode, SelectHTMLAttributes } from "react";

function Chevron() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="m6 9 6 6 6-6" />
    </svg>
  );
}

export function MeetingIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M6.75 3v2.25M17.25 3v2.25M3.75 8.25h16.5M4.5 6.75h15A1.5 1.5 0 0 1 21 8.25v10.5A1.5 1.5 0 0 1 19.5 20.25h-15A1.5 1.5 0 0 1 3 18.75V8.25A1.5 1.5 0 0 1 4.5 6.75Z"
      />
    </svg>
  );
}

export function PersonIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
      <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 7.5a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 19.5a7.5 7.5 0 0 1 15 0" />
    </svg>
  );
}

export function FilterSelect({
  icon,
  active = false,
  className = "",
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & {
  icon?: ReactNode;
  active?: boolean;
}) {
  return (
    <div className={`relative grid min-w-0 ${className}`}>
      {icon ? (
        <span
          className={`pointer-events-none absolute inset-y-0 left-3 z-10 flex items-center ${
            active ? "text-teal-600 dark:text-teal-300" : "text-slate-400"
          }`}
        >
          {icon}
        </span>
      ) : null}
      <select
        {...props}
        className={`h-10 w-full min-w-0 max-w-full cursor-pointer appearance-none truncate rounded-xl border text-sm outline-none transition ${
          icon ? "pl-9" : "pl-3"
        } pr-9 ${
          active
            ? "border-teal-500 bg-teal-50 font-medium text-teal-950 dark:border-teal-500 dark:bg-teal-950/60 dark:text-teal-50"
            : "border-slate-200 bg-white text-slate-800 dark:border-teal-800 dark:bg-[#0c1c1b] dark:text-teal-50"
        } focus:border-teal-500 dark:focus:border-teal-500`}
      >
        {children}
      </select>
      <span className="pointer-events-none absolute inset-y-0 right-3 z-10 flex items-center text-slate-400">
        <Chevron />
      </span>
    </div>
  );
}

export function SelectWrap({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`relative grid min-w-0 w-full ${className}`}>
      {children}
      <span className="pointer-events-none absolute inset-y-0 right-3 z-10 flex items-center text-slate-400">
        <Chevron />
      </span>
    </div>
  );
}
