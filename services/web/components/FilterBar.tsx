"use client";

import type { ChatFilters } from "@/lib/api";
import { ChevronDownIcon } from "@/components/icons";

interface FilterBarProps {
  filters: ChatFilters;
  onChange: (next: ChatFilters) => void;
  availableProjects: string[];
  availableSettlements: string[];
}

function toggle(list: string[] | undefined, value: string): string[] {
  const current = list ?? [];
  return current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
}

function FilterDropdown({
  label,
  summary,
  children,
}: {
  label: string;
  summary: string;
  children: React.ReactNode;
}) {
  return (
    <details className="group relative">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 rounded-chip border border-keso-border bg-white px-3 py-1.5 text-[12.5px] text-keso-ink [&::-webkit-details-marker]:hidden [&::marker]:hidden">
        {summary}
        <ChevronDownIcon className="text-keso-ink-faint transition-transform group-open:rotate-180" />
      </summary>
      <div className="absolute left-0 top-[calc(100%+6px)] z-10 min-w-[200px] rounded-xl border border-keso-border bg-white p-3 shadow-lg">
        <div className="mb-2 text-[11px] font-bold uppercase tracking-wider text-keso-ink-faint">{label}</div>
        {children}
      </div>
    </details>
  );
}

export function FilterBar({ filters, onChange, availableProjects, availableSettlements }: FilterBarProps) {
  const settlementSummary =
    !filters.settlement_ids?.length
      ? "All settlements"
      : filters.settlement_ids.length === 1
        ? `Settlement ${filters.settlement_ids[0]}`
        : `Settlements ${filters.settlement_ids.join(", ")}`;

  const projectSummary = !filters.project_ids?.length ? "All projects" : `${filters.project_ids.length} project(s)`;

  const dateSummary = filters.date_from || filters.date_to ? "Custom range" : "Any date";

  return (
    <div className="flex shrink-0 items-center gap-2 border-t border-keso-border-soft px-10 py-2.5">
      <span className="mr-0.5 text-[11.5px] font-semibold text-keso-ink-faint">Filters</span>

      <FilterDropdown label="Projects" summary={projectSummary}>
        {availableProjects.length === 0 ? (
          <p className="text-[12.5px] text-keso-ink-faint">No project scope assigned.</p>
        ) : (
          <div className="flex flex-col gap-1.5">
            {availableProjects.map((id) => (
              <label key={id} className="flex items-center gap-2 text-[13px] text-keso-ink">
                <input
                  type="checkbox"
                  checked={filters.project_ids?.includes(id) ?? false}
                  onChange={() => onChange({ ...filters, project_ids: toggle(filters.project_ids, id) })}
                  className="accent-keso-indigo"
                />
                {id}
              </label>
            ))}
          </div>
        )}
      </FilterDropdown>

      <FilterDropdown label="Settlements" summary={settlementSummary}>
        {availableSettlements.length === 0 ? (
          <p className="text-[12.5px] text-keso-ink-faint">No settlement scope assigned.</p>
        ) : (
          <div className="flex flex-col gap-1.5">
            {availableSettlements.map((id) => (
              <label key={id} className="flex items-center gap-2 text-[13px] text-keso-ink">
                <input
                  type="checkbox"
                  checked={filters.settlement_ids?.includes(id) ?? false}
                  onChange={() => onChange({ ...filters, settlement_ids: toggle(filters.settlement_ids, id) })}
                  className="accent-keso-indigo"
                />
                Settlement {id}
              </label>
            ))}
          </div>
        )}
      </FilterDropdown>

      <FilterDropdown label="Date range" summary={dateSummary}>
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1 text-[12px] text-keso-ink-muted">
            From
            <input
              type="date"
              value={filters.date_from ?? ""}
              onChange={(e) => onChange({ ...filters, date_from: e.target.value || undefined })}
              className="rounded-md border border-keso-border px-2 py-1 text-[13px] text-keso-ink"
            />
          </label>
          <label className="flex flex-col gap-1 text-[12px] text-keso-ink-muted">
            To
            <input
              type="date"
              value={filters.date_to ?? ""}
              onChange={(e) => onChange({ ...filters, date_to: e.target.value || undefined })}
              className="rounded-md border border-keso-border px-2 py-1 text-[13px] text-keso-ink"
            />
          </label>
        </div>
      </FilterDropdown>
    </div>
  );
}
