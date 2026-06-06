import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { getStatusBadgeClass } from "./status";

// Adapted for this Vite app from ephraimduncan/blocks sidebar-02, table-03, and stats card patterns.
export type BlocksSidebarView = "overview" | "all" | "assigned" | "high" | "pending";
export type BlocksSidebarCounts = Record<Exclude<BlocksSidebarView, "overview">, number>;

export type BlocksTicket = {
  id: number;
  title: string;
  customer: string;
  priority: string;
  status: string;
  updatedAt: string;
};

export function BlocksSidebar({
  activeView,
  counts,
  onNavigate,
  onLogout,
  onSelectTicket,
  profile,
  search,
  setSearch,
  tickets,
}: {
  activeView: BlocksSidebarView;
  counts: BlocksSidebarCounts;
  onNavigate: (view: BlocksSidebarView) => void;
  onLogout: () => void;
  onSelectTicket: (ticketId: number) => void;
  profile: {
    email: string;
    name: string;
    role: string;
  };
  search: string;
  setSearch: (search: string) => void;
  tickets: BlocksTicket[];
}) {
  const [commandOpen, setCommandOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [signOutOpen, setSignOutOpen] = useState(false);
  const profileMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!profileOpen) {
      return;
    }

    const closeProfileOnOutsideClick = (event: PointerEvent) => {
      if (profileMenuRef.current?.contains(event.target as Node)) {
        return;
      }

      setProfileOpen(false);
    };

    document.addEventListener("pointerdown", closeProfileOnOutsideClick);
    return () => document.removeEventListener("pointerdown", closeProfileOnOutsideClick);
  }, [profileOpen]);

  return (
    <aside
      className="flex h-screen w-[220px] shrink-0 flex-col border-r border-border bg-sidebar px-2.5 py-3 text-sm"
      aria-label="Service desk navigation"
    >
      <button
        className="flex h-9 w-full items-center justify-between rounded-lg border border-border bg-background px-3 text-left text-[13px] text-muted-foreground transition hover:border-primary/40 hover:text-foreground"
        onClick={() => setCommandOpen(true)}
        type="button"
      >
        <span className="truncate">{search ? `Filter: ${search}` : "Search tickets..."}</span>
        <kbd className="ml-2 rounded-full border border-border bg-background px-1.5 py-0.5 font-mono text-[10px] font-normal">
          ⌘K
        </kbd>
      </button>

      <nav className="mt-3 flex-1 space-y-1" aria-label="Dashboard navigation">
        <BlocksSidebarItem
          active={activeView === "overview"}
          label="Overview"
          onClick={() => onNavigate("overview")}
          variant="parent"
        />
        <BlocksSidebarItem
          active={activeView === "all"}
          count={counts.all}
          label="All tickets"
          onClick={() => onNavigate("all")}
          variant="parent"
        />
        <div className="ml-4 space-y-1 border-l border-border pl-2" aria-label="Ticket views">
          <BlocksSidebarItem
            active={activeView === "assigned"}
            count={counts.assigned}
            label="Assigned to me"
            onClick={() => onNavigate("assigned")}
            variant="child"
          />
          <BlocksSidebarItem
            active={activeView === "high"}
            count={counts.high}
            label="High priority"
            onClick={() => onNavigate("high")}
            variant="child"
          />
          <BlocksSidebarItem
            active={activeView === "pending"}
            count={counts.pending}
            label="Pending approval"
            onClick={() => onNavigate("pending")}
            variant="child"
          />
        </div>
      </nav>

      <div className="relative border-t border-border pt-2" ref={profileMenuRef}>
        <button
          aria-expanded={profileOpen}
          aria-haspopup="menu"
          className="group flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left transition hover:bg-muted"
          onClick={() => setProfileOpen((current) => !current)}
          type="button"
        >
          <span className="flex aspect-square size-8 shrink-0 items-center justify-center rounded-lg border border-border bg-background text-xs font-normal text-foreground">
            {profile.name.slice(0, 1)}
          </span>
          <span className="grid min-w-0 flex-1 text-left leading-tight">
            <span className="truncate text-[13px] font-normal text-foreground">{profile.name}</span>
            <span className="block truncate text-xs text-muted-foreground">{profile.email}</span>
          </span>
          <ChevronsUpDownIcon />
        </button>

        {profileOpen ? (
          <div className="absolute bottom-14 left-1 right-1 z-20 rounded-lg border border-border bg-card p-2">
            <div className="border-b border-border px-2 py-2">
              <p className="text-[13px] font-medium text-foreground">{profile.name}</p>
              <p className="truncate text-xs text-muted-foreground">{profile.role}</p>
            </div>
            <button
              className="mt-1 block w-full rounded-full px-2 py-2 text-left text-[13px] font-normal text-primary hover:bg-primary/10"
              onClick={() => {
                setProfileOpen(false);
                setSignOutOpen(true);
              }}
              type="button"
            >
              Sign out
            </button>
          </div>
        ) : null}
      </div>

      <BlocksCommandMenu
        activeView={activeView}
        onNavigate={onNavigate}
        onOpenChange={setCommandOpen}
        onSelectTicket={onSelectTicket}
        open={commandOpen}
        search={search}
        setSearch={setSearch}
        tickets={tickets}
      />
      <BlocksConfirmDialog
        confirmLabel="Sign out"
        description="This ends the current mock technician session and returns to the login screen."
        onConfirm={onLogout}
        onOpenChange={setSignOutOpen}
        open={signOutOpen}
        title="Sign out?"
        tone="danger"
      />
    </aside>
  );
}

function BlocksCommandMenu({
  activeView,
  onNavigate,
  onOpenChange,
  onSelectTicket,
  open,
  search,
  setSearch,
  tickets,
}: {
  activeView: BlocksSidebarView;
  onNavigate: (view: BlocksSidebarView) => void;
  onOpenChange: (open: boolean) => void;
  onSelectTicket: (ticketId: number) => void;
  open: boolean;
  search: string;
  setSearch: (search: string) => void;
  tickets: BlocksTicket[];
}) {
  const [inputValue, setInputValue] = useState(search);

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onOpenChange(!open);
      }

      if (event.key === "Escape" && open) {
        onOpenChange(false);
      }
    };

    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, [onOpenChange, open]);

  useEffect(() => {
    if (open) {
      setInputValue(search);
    }
  }, [open, search]);

  const matchingTickets = useMemo(() => {
    const query = inputValue.trim().toLowerCase();

    if (!query) {
      return tickets.slice(0, 5);
    }

    return tickets
      .filter(
        (ticket) =>
          ticket.title.toLowerCase().includes(query) ||
          ticket.customer.toLowerCase().includes(query) ||
          ticket.priority.toLowerCase().includes(query) ||
          ticket.status.toLowerCase().includes(query) ||
          String(ticket.id).includes(query),
      )
      .slice(0, 6);
  }, [inputValue, tickets]);

  if (!open) {
    return null;
  }

  const close = () => onOpenChange(false);
  const navigate = (view: BlocksSidebarView) => {
    onNavigate(view);
    close();
  };
  const selectTicket = (ticketId: number) => {
    onSelectTicket(ticketId);
    close();
  };
  const applyFilter = () => {
    setSearch(inputValue);
    onNavigate("all");
    close();
  };

  return (
    <div
      className="fixed inset-0 z-40 grid place-items-start justify-center bg-background/80 px-4 pt-[12vh]"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          close();
        }
      }}
      role="presentation"
    >
      <div className="w-full max-w-xl overflow-hidden rounded-xl border border-border bg-card" role="dialog" aria-modal="true" aria-labelledby="command-menu-title">
        <div className="sr-only">
          <h2 id="command-menu-title">Command menu</h2>
          <p>Use the command menu to navigate and search tickets.</p>
        </div>
        <div className="flex h-12 items-center gap-2 border-b border-border px-4">
          <SearchIcon />
          <input
            autoFocus
            className="h-10 flex-1 border-0 bg-transparent px-0 text-[15px] outline-none focus:ring-0"
            onChange={(event) => setInputValue(event.target.value)}
            placeholder="Search tickets or actions..."
            value={inputValue}
          />
          <button className="flex shrink-0 items-center" onClick={close} type="button">
            <kbd className="rounded-full border border-border bg-background px-2 py-1 font-mono text-[10px] text-muted-foreground">
              Esc
            </kbd>
          </button>
        </div>

        <div className="max-h-[430px] overflow-auto py-2">
          <CommandGroup heading="Navigation">
            <CommandItem active={activeView === "overview"} label="Overview" meta="⌘ 1" onSelect={() => navigate("overview")} />
            <CommandItem active={activeView === "all"} label="All tickets" meta="⌘ 2" onSelect={() => navigate("all")} />
            <CommandItem active={activeView === "assigned"} label="Assigned to me" onSelect={() => navigate("assigned")} />
            <CommandItem active={activeView === "high"} label="High priority" onSelect={() => navigate("high")} />
            <CommandItem active={activeView === "pending"} label="Pending approval" onSelect={() => navigate("pending")} />
          </CommandGroup>

          <CommandGroup heading="Tickets">
            {matchingTickets.length ? (
              matchingTickets.map((ticket) => (
                <CommandItem
                  description={`${ticket.customer} · ${ticket.priority} · ${ticket.status}`}
                  key={ticket.id}
                  label={ticket.title}
                  meta={`#${ticket.id}`}
                  onSelect={() => selectTicket(ticket.id)}
                />
              ))
            ) : (
              <p className="px-4 py-3 text-sm text-muted-foreground">No tickets found.</p>
            )}
          </CommandGroup>

          <CommandGroup heading="Quick actions">
            <CommandItem
              description={inputValue ? `Set ticket queue filter to "${inputValue}"` : "Clear the ticket queue search filter"}
              label={inputValue ? "Apply queue filter" : "Clear queue filter"}
              meta="Enter"
              onSelect={applyFilter}
            />
          </CommandGroup>
        </div>
      </div>
    </div>
  );
}

function CommandGroup({ children, heading }: { children: ReactNode; heading: string }) {
  return (
    <div className="py-1">
      <p className="px-4 py-1 font-mono text-[11px] uppercase text-muted-foreground">{heading}</p>
      <div>{children}</div>
    </div>
  );
}

export function BlocksConfirmDialog({
  cancelLabel = "Cancel",
  confirmLabel,
  description,
  onConfirm,
  onOpenChange,
  open,
  title,
  tone = "default",
}: {
  cancelLabel?: string;
  confirmLabel: string;
  description: string;
  onConfirm: () => void;
  onOpenChange: (open: boolean) => void;
  open: boolean;
  title: string;
  tone?: "danger" | "default" | "success" | "warning";
}) {
  if (!open) {
    return null;
  }

  const confirm = () => {
    onConfirm();
    onOpenChange(false);
  };
  const toneClasses = {
    danger: {
      button: "button button-danger",
      icon: "border-severity-critical/45 bg-severity-critical/10 text-severity-critical",
    },
    default: {
      button: "button button-dark",
      icon: "border-state-open/45 bg-state-open/10 text-state-open",
    },
    success: {
      button: "button button-success",
      icon: "border-severity-low/45 bg-severity-low/10 text-severity-low",
    },
    warning: {
      button: "button button-warning",
      icon: "border-severity-medium/45 bg-severity-medium/10 text-severity-medium",
    },
  }[tone];

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-background/80 px-4" role="presentation">
      <section
        aria-labelledby="confirm-dialog-title"
        aria-modal="true"
        className="flex w-full max-w-sm flex-col items-center rounded-xl border border-border bg-card p-5 text-center"
        role="dialog"
      >
        <div
          className={[
            "mb-4 flex size-11 items-center justify-center rounded-full border",
            toneClasses.icon,
          ].join(" ")}
        >
          <WarningIcon />
        </div>
        <h2 className="text-balance text-xl font-normal" id="confirm-dialog-title">
          {title}
        </h2>
        <p className="mt-2 text-pretty text-sm leading-6 text-muted-foreground">{description}</p>
        <div className="mt-5 grid w-full grid-cols-2 gap-2">
          <button className={toneClasses.button} onClick={confirm} type="button">
            {confirmLabel}
          </button>
          <button className="button" onClick={() => onOpenChange(false)} type="button">
            {cancelLabel}
          </button>
        </div>
      </section>
    </div>
  );
}

function CommandItem({
  active,
  description,
  label,
  meta,
  onSelect,
}: {
  active?: boolean;
  description?: string;
  label: string;
  meta?: string;
  onSelect: () => void;
}) {
  return (
    <button
      className={[
        "mx-2 flex w-[calc(100%-1rem)] items-center gap-3 rounded-lg px-3 py-2.5 text-left transition hover:bg-muted",
        active ? "bg-muted text-foreground" : "text-foreground",
      ].join(" ")}
      onClick={onSelect}
      type="button"
    >
      <ArrowRightIcon />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm">{label}</span>
        {description ? <span className="block truncate text-xs text-muted-foreground">{description}</span> : null}
      </span>
      {meta ? (
        <span className="ml-auto rounded-full border border-border bg-background px-2 py-1 font-mono text-[10px] text-muted-foreground">
          {meta}
        </span>
      ) : null}
    </button>
  );
}

function BlocksSidebarItem({
  active,
  count,
  label,
  onClick,
  variant,
}: {
  active: boolean;
  count?: number;
  label: string;
  onClick: () => void;
  variant: "parent" | "child";
}) {
  return (
    <button
      className={[
        "group flex h-8 w-full items-center justify-between rounded-full px-2 text-left text-[13px] transition",
        variant === "child" ? "font-normal text-muted-foreground" : "font-normal text-foreground",
        active
          ? "bg-muted text-foreground"
          : "text-muted-foreground hover:bg-muted/70 hover:text-foreground",
      ].join(" ")}
      onClick={onClick}
      type="button"
    >
      <span className="truncate">{label}</span>
      {typeof count === "number" ? (
        <span className="ml-2 min-w-5 rounded-full bg-background px-1.5 py-0.5 text-center font-mono text-[11px] font-normal text-muted-foreground">
          {count}
        </span>
      ) : null}
    </button>
  );
}

export function BlocksTicketTable({
  onSelectTicket,
  tickets,
}: {
  onSelectTicket: (ticketId: number) => void;
  tickets: BlocksTicket[];
}) {
  return (
    <table className="w-full table-fixed border-separate border-spacing-0 text-sm">
      <colgroup>
        <col className="w-[28%]" />
        <col className="w-[28%]" />
        <col className="w-[13%]" />
        <col className="w-[12%]" />
        <col className="w-[14%]" />
        <col className="w-[5%]" />
      </colgroup>
      <thead className="bg-background">
        <tr className="border-b bg-background hover:bg-background">
          <TableHead>Ticket</TableHead>
          <TableHead>Customer</TableHead>
          <TableHead>Priority</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Updated</TableHead>
          <th className="h-11 w-12 border-b border-border bg-background px-4" />
        </tr>
      </thead>
      <tbody>
        {tickets.length ? (
          tickets.map((ticket) => (
            <tr
              className="group cursor-pointer outline-none transition hover:bg-muted/40 focus-visible:bg-muted/50"
              key={ticket.id}
              onClick={() => onSelectTicket(ticket.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelectTicket(ticket.id);
                }
              }}
              role="button"
              tabIndex={0}
            >
              <td className="h-14 border-b border-border px-4 align-middle">
                <strong className="block font-normal text-foreground">{ticket.title}</strong>
                <span className="font-mono text-xs text-muted-foreground">#{ticket.id}</span>
              </td>
              <td className="h-14 border-b border-border px-4 align-middle text-muted-foreground">
                {ticket.customer}
              </td>
              <td className="h-14 border-b border-border px-4 align-middle">
                <BlocksStatusBadge label={ticket.priority} />
              </td>
              <td className="h-14 border-b border-border px-4 align-middle">
                <BlocksStatusBadge label={ticket.status} />
              </td>
              <td className="h-14 border-b border-border px-4 align-middle text-muted-foreground">
                {formatTicketDate(ticket.updatedAt)}
              </td>
              <td className="h-14 border-b border-border px-4 text-right align-middle">
                <span className="inline-flex size-7 items-center justify-center rounded-full border border-border text-muted-foreground transition group-hover:text-foreground">
                  <ArrowRightIcon />
                </span>
              </td>
            </tr>
          ))
        ) : (
          <tr>
            <td className="h-24 px-4 text-center text-muted-foreground" colSpan={6}>
              No tickets found matching the selected filters.
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

function TableHead({ children }: { children: string }) {
  return (
    <th className="h-11 border-b border-border bg-background px-4 text-left font-mono text-xs font-normal uppercase text-muted-foreground">
      {children}
    </th>
  );
}

function BlocksStatusBadge({ label }: { label: string }) {
  return (
    <span
      className={[
        "inline-flex whitespace-nowrap rounded-full border px-2.5 py-1 font-mono text-[11px] font-normal uppercase leading-none",
        getStatusBadgeClass(label),
      ].join(" ")}
    >
      {label}
    </span>
  );
}

type BlocksStatTone = "positive" | "negative" | "neutral";
type BlocksStatKind = "chart" | "metric" | "status" | "timestamp";

export type BlocksStat = {
  label: string;
  value: number | string;
  change?: string;
  code?: string;
  kind?: BlocksStatKind;
  tone?: BlocksStatTone;
};

export function BlocksStatsGrid({
  density = "default",
  stats,
}: {
  density?: "default" | "compact";
  stats: BlocksStat[];
}) {
  return (
    <section
      className={[
        "mb-6 grid grid-cols-1 gap-4 md:grid-cols-2",
        density === "compact" ? "xl:grid-cols-4" : "xl:grid-cols-6",
      ].join(" ")}
      aria-label="Queue statistics"
    >
      {stats.map((stat, index) => (
        stat.kind === "chart" ? (
          <BlocksChartStatCard density={density} index={index} key={stat.label} stat={stat} />
        ) : (
          <BlocksSimpleStatCard density={density} key={stat.label} stat={stat} />
        )
      ))}
    </section>
  );
}

function BlocksChartStatCard({
  density,
  index,
  stat,
}: {
  density: "default" | "compact";
  index: number;
  stat: BlocksStat;
}) {
  const tone = stat.tone ?? inferStatTone(stat.label);
  const styles = statToneStyles[tone];
  const change = stat.change ?? inferStatChange(stat.label, stat.value);

  return (
    <article
      className={[
        "flex min-h-[166px] flex-col overflow-hidden rounded-lg border border-border bg-card",
        density === "default" ? "xl:col-span-3" : "",
      ].join(" ")}
    >
      <div className="grid min-h-[58px] grid-cols-[minmax(0,1fr)_auto] items-start gap-4 px-4 pt-4">
        <div className="min-w-0">
          <p className="truncate text-[15px] font-normal leading-5 text-foreground">
            {stat.label}
            {stat.code ? <span className="ml-1 font-medium text-muted-foreground">({stat.code})</span> : null}
          </p>
          <strong
            className={[
              "mt-1 block max-w-full truncate text-[clamp(1.35rem,1.8vw,1.7rem)] font-normal leading-tight tabular-nums",
              styles.value,
            ].join(" ")}
          >
            {stat.value}
          </strong>
        </div>
        {change ? (
          <span className={["mt-8 whitespace-nowrap text-sm font-medium tabular-nums", styles.change].join(" ")}>
            {change}
          </span>
        ) : null}
      </div>
      <BlocksAreaChart color={styles.chart} index={index} />
    </article>
  );
}

function BlocksSimpleStatCard({
  density,
  stat,
}: {
  density: "default" | "compact";
  stat: BlocksStat;
}) {
  const tone = stat.tone ?? inferStatTone(stat.label);
  const styles = statToneStyles[tone];
  const change = stat.change ?? inferStatChange(stat.label, stat.value);
  const isStatus = stat.kind === "status";

  return (
    <article
      className={[
        "flex flex-col justify-between self-start border-l border-border px-4 py-2",
        density === "compact" ? "min-h-[74px]" : "min-h-[92px]",
        density === "default" ? "xl:col-span-2" : "",
      ].join(" ")}
    >
      <div>
        <p className="font-mono text-[11px] font-normal uppercase tracking-normal text-muted-foreground">{stat.label}</p>
        {isStatus ? (
          <div className="mt-3">
            <BlocksStatusBadge label={String(stat.value)} />
          </div>
        ) : (
          <strong
            className={[
              "mt-3 block max-w-full truncate font-normal leading-tight tabular-nums",
              density === "compact" ? "text-xl" : "text-[clamp(1.45rem,2vw,2rem)]",
              styles.value,
            ].join(" ")}
          >
            {stat.value}
          </strong>
        )}
      </div>
      {change ? (
        <span className={["mt-3 block font-mono text-[11px] font-normal uppercase", styles.change].join(" ")}>
          {change}
        </span>
      ) : null}
    </article>
  );
}

const statToneStyles = {
  positive: {
    chart: "#a0c3ec",
    change: "text-accent-breeze",
    value: "text-accent-breeze",
  },
  negative: {
    chart: "#ff7a17",
    change: "text-accent-sunset",
    value: "text-accent-sunset",
  },
  neutral: {
    chart: "#8a8f98",
    change: "text-muted-foreground",
    value: "text-foreground",
  },
} satisfies Record<
  BlocksStatTone,
  {
    chart: string;
    change: string;
    value: string;
  }
>;

function BlocksAreaChart({ color, index }: { color: string; index: number }) {
  const paths = [
    "M0 48 C22 45 36 47 52 39 C70 30 86 41 102 34 C121 25 137 57 158 45 C180 32 205 24 228 32 C244 36 253 28 260 23",
    "M0 44 C18 47 31 48 48 42 C66 35 82 43 100 50 C121 60 142 48 164 43 C189 36 211 24 238 30 C249 33 254 28 260 24",
    "M0 50 C20 40 38 34 56 42 C72 49 87 31 104 23 C126 13 145 55 166 41 C186 28 209 38 228 33 C244 29 252 20 260 13",
    "M0 38 C20 36 35 37 50 43 C68 51 83 34 101 34 C123 34 140 25 160 21 C181 17 200 34 220 27 C240 20 250 11 260 8",
    "M0 54 C23 54 35 55 52 39 C70 23 86 45 103 35 C121 23 138 15 156 30 C177 47 197 34 218 41 C240 49 249 36 260 31",
    "M0 43 C18 43 34 43 50 37 C67 31 82 48 98 40 C117 30 134 14 153 21 C173 28 194 25 213 20 C235 14 248 16 260 10",
  ];
  const linePath = paths[index % paths.length];
  const fillPath = `${linePath} L260 78 L0 78 Z`;
  const gradientId = `blocks-area-gradient-${index}`;

  return (
    <svg
      aria-hidden="true"
      className="mt-5 h-[82px] w-full shrink-0"
      preserveAspectRatio="none"
      viewBox="0 0 260 78"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.18" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={fillPath} fill={`url(#${gradientId})`} />
      <path d={linePath} fill="none" stroke={color} strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.25" />
    </svg>
  );
}

function inferStatTone(label: string): BlocksStatTone {
  const normalized = label.toLowerCase();

  if (normalized.includes("high priority")) {
    return "negative";
  }

  if (normalized.includes("validation") || normalized.includes("connection") || normalized.includes("activity")) {
    return "neutral";
  }

  return "positive";
}

function inferStatChange(label: string, value: BlocksStat["value"]) {
  const normalized = label.toLowerCase();

  if (normalized.includes("newest")) {
    return "Latest";
  }

  if (normalized.includes("activity") || normalized.includes("validation") || normalized.includes("connection")) {
    return "";
  }

  if (typeof value === "number") {
    return value === 0 ? "0.0%" : `+${value} (${Math.max(4, value * 5.2).toFixed(1)}%)`;
  }

  return "";
}

function SearchIcon() {
  return (
    <svg aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" fill="none" viewBox="0 0 24 24">
      <path
        d="m20 20-4.3-4.3m1.8-5.2a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.7"
      />
    </svg>
  );
}

function ArrowRightIcon() {
  return (
    <svg aria-hidden="true" className="size-4 shrink-0 text-current opacity-70" fill="none" viewBox="0 0 24 24">
      <path d="M5 12h14m-5-5 5 5-5 5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
    </svg>
  );
}

function ChevronsUpDownIcon() {
  return (
    <svg aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" fill="none" viewBox="0 0 24 24">
      <path d="m8 9 4-4 4 4m0 6-4 4-4-4" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
    </svg>
  );
}

function WarningIcon() {
  return (
    <svg aria-hidden="true" className="size-5" fill="none" viewBox="0 0 24 24">
      <path
        d="M12 8v5m0 3.5h.01M10.2 4.9 2.7 18a2 2 0 0 0 1.7 3h15.2a2 2 0 0 0 1.7-3L13.8 4.9a2.1 2.1 0 0 0-3.6 0Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.7"
      />
    </svg>
  );
}

function GearIcon() {
  return (
    <svg aria-hidden="true" className="size-4" fill="none" viewBox="0 0 24 24">
      <path
        d="M12 8.75A3.25 3.25 0 1 0 12 15.25A3.25 3.25 0 0 0 12 8.75Z"
        stroke="currentColor"
        strokeWidth="1.7"
      />
      <path
        d="M18.22 13.2c.06-.39.09-.79.09-1.2s-.03-.81-.09-1.2l2.02-1.53-1.95-3.38-2.36.96a8.02 8.02 0 0 0-2.08-1.2L13.5 3h-3l-.35 2.65c-.74.28-1.44.68-2.08 1.2l-2.36-.96-1.95 3.38 2.02 1.53c-.06.39-.09.79-.09 1.2s.03.81.09 1.2l-2.02 1.53 1.95 3.38 2.36-.96c.64.52 1.34.92 2.08 1.2L10.5 21h3l.35-2.65c.74-.28 1.44-.68 2.08-1.2l2.36.96 1.95-3.38-2.02-1.53Z"
        stroke="currentColor"
        strokeLinejoin="round"
        strokeWidth="1.7"
      />
    </svg>
  );
}

function formatTicketDate(value: string) {
  return new Date(value).toLocaleString([], {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
