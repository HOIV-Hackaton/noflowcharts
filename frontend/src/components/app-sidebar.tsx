"use client";

import {
	AlertTriangleIcon,
	ClipboardListIcon,
	ClockIcon,
	InboxIcon,
	LayoutDashboardIcon,
	SearchIcon,
	ShieldCheckIcon,
} from "lucide-react";

import { NavUser } from "@/components/nav-user";
import type { SidebarCounts, SidebarView } from "@/components/service-desk-ui";
import { StatusLabel } from "@/components/service-desk-ui";
import { Input } from "@/components/ui/input";
import {
	Sidebar,
	SidebarContent,
	SidebarFooter,
	SidebarGroup,
	SidebarGroupContent,
	SidebarGroupLabel,
	SidebarHeader,
	SidebarMenu,
	SidebarMenuBadge,
	SidebarMenuButton,
	SidebarMenuItem,
} from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";
import type { Ticket } from "@/types";

const navItems: Array<{
	icon: typeof LayoutDashboardIcon;
	label: string;
	view: SidebarView;
}> = [
	{ icon: LayoutDashboardIcon, label: "Overview", view: "overview" },
	{ icon: InboxIcon, label: "All tickets", view: "all" },
	{ icon: ClipboardListIcon, label: "Assigned", view: "assigned" },
	{ icon: AlertTriangleIcon, label: "High priority", view: "high" },
	{ icon: ClockIcon, label: "Pending approval", view: "pending" },
];

export function AppSidebar({
	activeView,
	counts,
	onLogout,
	onNavigate,
	onSelectTicket,
	profile,
	search,
	setSearch,
	tickets,
}: {
	activeView: SidebarView;
	counts: SidebarCounts;
	onLogout: () => void;
	onNavigate: (view: SidebarView) => void;
	onSelectTicket: (ticketId: number) => void;
	profile: {
		email: string;
		name: string;
		role: string;
	};
	search: string;
	setSearch: (search: string) => void;
	tickets: Ticket[];
}) {
	const focusTickets = tickets
		.filter((ticket) => ticket.priority === "Critical" || ticket.status === "PENDING")
		.slice(0, 4);

	return (
		<Sidebar
			className={cn(
				"*:data-[slot=sidebar-inner]:bg-sidebar",
				"**:data-[slot=sidebar-menu-button]:[&>span]:text-sidebar-foreground/75"
			)}
			collapsible="icon"
			variant="sidebar"
		>
			<SidebarHeader className="h-16 justify-center border-b px-2">
				<SidebarMenu>
					<SidebarMenuItem>
						<SidebarMenuButton asChild size="lg">
							<button onClick={() => onNavigate("overview")} type="button">
								<span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
									<ShieldCheckIcon />
								</span>
								<span className="grid text-left leading-tight">
									<span className="font-medium text-sidebar-foreground">techbold</span>
									<span className="text-xs text-muted-foreground">service desk</span>
								</span>
							</button>
						</SidebarMenuButton>
					</SidebarMenuItem>
				</SidebarMenu>
			</SidebarHeader>
			<SidebarContent>
				<SidebarGroup>
					<SidebarGroupLabel>Queue</SidebarGroupLabel>
					<SidebarGroupContent>
						<label className="relative mb-2 block px-2">
							<SearchIcon className="pointer-events-none absolute top-1/2 left-4 -translate-y-1/2 text-muted-foreground" />
							<Input
								className="pl-8"
								onChange={(event) => setSearch(event.target.value)}
								placeholder="Search tickets"
								value={search}
							/>
						</label>
						<SidebarMenu>
							{navItems.map((item) => {
								const Icon = item.icon;
								const count = item.view === "overview" ? null : counts[item.view];

								return (
									<SidebarMenuItem key={item.view}>
										<SidebarMenuButton
											isActive={activeView === item.view}
											onClick={() => onNavigate(item.view)}
										>
											<Icon />
											<span>{item.label}</span>
										</SidebarMenuButton>
										{count !== null ? <SidebarMenuBadge>{count}</SidebarMenuBadge> : null}
									</SidebarMenuItem>
								);
							})}
						</SidebarMenu>
					</SidebarGroupContent>
				</SidebarGroup>

				<SidebarGroup>
					<SidebarGroupLabel>Focus</SidebarGroupLabel>
					<SidebarGroupContent>
						<SidebarMenu>
							{focusTickets.length ? (
								focusTickets.map((ticket) => (
									<SidebarMenuItem key={ticket.id}>
										<SidebarMenuButton
											className="h-auto items-start py-2"
											onClick={() => onSelectTicket(ticket.id)}
										>
											<span className="grid min-w-0 gap-1">
												<span className="truncate text-sm">{ticket.title}</span>
												<span className="flex items-center gap-1">
													<StatusLabel label={ticket.priority} />
													<StatusLabel label={ticket.status} />
												</span>
											</span>
										</SidebarMenuButton>
									</SidebarMenuItem>
								))
							) : (
								<SidebarMenuItem>
									<SidebarMenuButton disabled>No priority tickets</SidebarMenuButton>
								</SidebarMenuItem>
							)}
						</SidebarMenu>
					</SidebarGroupContent>
				</SidebarGroup>
			</SidebarContent>
			<SidebarFooter className="border-t p-2">
				<NavUser onLogout={onLogout} user={profile} />
			</SidebarFooter>
		</Sidebar>
	);
}
