/** Shared inline icons -- stroke-based, 24px viewBox, matching the KESO Assistant design canvas. */

interface IconProps {
  className?: string;
  size?: number;
}

const base = {
  viewBox: "0 0 24 24",
  fill: "none",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

export function BotIcon({ className, size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} className={className} stroke="currentColor" {...base}>
      <rect x="4" y="8" width="16" height="12" rx="3" />
      <path d="M9 8V6a3 3 0 0 1 6 0v2" />
      <line x1="9" y1="14" x2="9" y2="14.01" />
      <line x1="15" y1="14" x2="15" y2="14.01" />
      <line x1="12" y1="2" x2="12" y2="4" />
    </svg>
  );
}

export function SendIcon({ className, size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} className={className} stroke="currentColor" {...base} strokeWidth={2.25}>
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}

export function SearchIcon({ className, size = 15 }: IconProps) {
  return (
    <svg width={size} height={size} className={className} stroke="currentColor" {...base}>
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

export function PlusIcon({ className, size = 16 }: IconProps) {
  return (
    <svg width={size} height={size} className={className} stroke="currentColor" {...base} strokeWidth={2.25}>
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

export function DocIcon({ className, size = 13 }: IconProps) {
  return (
    <svg width={size} height={size} className={className} stroke="currentColor" {...base}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}

export function RecordIcon({ className, size = 13 }: IconProps) {
  return (
    <svg width={size} height={size} className={className} stroke="currentColor" {...base}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <line x1="3" y1="10" x2="21" y2="10" />
      <line x1="8" y1="14" x2="8" y2="17" />
      <line x1="12" y1="14" x2="12" y2="17" />
    </svg>
  );
}

export function ChevronDownIcon({ className, size = 11 }: IconProps) {
  return (
    <svg width={size} height={size} className={className} stroke="currentColor" {...base} strokeWidth={2.5}>
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

export function UserIcon({ className, size = 12 }: IconProps) {
  return (
    <svg width={size} height={size} className={className} stroke="currentColor" {...base}>
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

export function ShieldCheckIcon({ className, size = 14 }: IconProps) {
  return (
    <svg width={size} height={size} className={className} stroke="currentColor" {...base} strokeWidth={2.25}>
      <path d="M9 12l2 2 4-4" />
      <circle cx="12" cy="12" r="10" />
    </svg>
  );
}

export function LockIcon({ className, size = 15 }: IconProps) {
  return (
    <svg width={size} height={size} className={className} stroke="currentColor" {...base}>
      <rect x="3" y="11" width="18" height="11" rx="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}

export function MailIcon({ className, size = 15 }: IconProps) {
  return (
    <svg width={size} height={size} className={className} stroke="currentColor" {...base}>
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <path d="m22 6-10 7L2 6" />
    </svg>
  );
}

export function LogOutIcon({ className, size = 14 }: IconProps) {
  return (
    <svg width={size} height={size} className={className} stroke="currentColor" {...base}>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  );
}
