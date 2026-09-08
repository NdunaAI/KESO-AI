import Image from "next/image";
import type { UserProfile } from "@/lib/api";
import { formatRoleLabel, initialsFromName } from "@/lib/format";
import { UserIcon } from "@/components/icons";

function scopeSummary(scope: UserProfile["scope"]): string {
  if (scope.settlements.includes("*")) return "All settlements";
  if (scope.settlements.length > 0) return `Settlements: ${scope.settlements.join(", ")}`;
  if (scope.projects.includes("*")) return "All projects";
  if (scope.projects.length > 0) return `Projects: ${scope.projects.join(", ")}`;
  return "No scope restrictions";
}

export function Header({ profile }: { profile: UserProfile | null }) {
  return (
    <header className="flex h-[72px] shrink-0 items-center justify-between border-b border-keso-border bg-white px-8">
      <div className="flex items-center gap-4">
        <Image src="/kuhle-logo.png" alt="Kuhle Solutions and Development Services" width={93} height={32} priority />
        <div className="h-7 w-px bg-keso-border" />
        <div className="flex items-baseline gap-2">
          <span className="text-[19px] font-bold tracking-tight text-keso-ink">KESO Assistant</span>
          <span className="text-[19px] leading-none">🤖</span>
        </div>
      </div>

      <div className="flex items-center gap-5">
        {profile ? (
          <>
            <div className="flex flex-col items-end gap-0.5">
              <div className="flex items-center gap-1.5 rounded-chip bg-keso-indigo-tint px-3 py-1 text-xs font-semibold text-keso-indigo">
                <UserIcon className="text-keso-indigo" />
                {formatRoleLabel(profile.roles[0] ?? "user")}
              </div>
              <span className="text-[11px] text-keso-ink-faint">{scopeSummary(profile.scope)}</span>
            </div>
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-keso-orange to-keso-indigo text-[13px] font-bold text-white">
              {initialsFromName(profile.display_name)}
            </div>
          </>
        ) : (
          <div className="rounded-chip bg-keso-surface px-3 py-1 text-xs font-medium text-keso-ink-faint">
            Not signed in
          </div>
        )}
      </div>
    </header>
  );
}
