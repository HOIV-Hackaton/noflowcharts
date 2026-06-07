"use client";

import { useEffect, useMemo, useState } from "react";
import {
	AlertTriangleIcon,
	ChevronDownIcon,
	ClipboardListIcon,
	InboxIcon,
	LayoutDashboardIcon,
	SearchIcon,
	TicketIcon,
} from "lucide-react";

import { NavUser } from "@/components/nav-user";
import type { SidebarCounts, SidebarView } from "@/components/service-desk-ui";
import { StatusLabel } from "@/components/service-desk-ui";
import {
	Command,
	CommandDialog,
	CommandEmpty,
	CommandGroup,
	CommandInput,
	CommandItem,
	CommandList,
	CommandSeparator,
	CommandShortcut,
} from "@/components/ui/command";
import { Kbd } from "@/components/ui/kbd";
import { Skeleton } from "@/components/ui/skeleton";
import {
	Collapsible,
	CollapsibleContent,
	CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
	Sidebar,
	SidebarContent,
	SidebarFooter,
	SidebarGroup,
	SidebarGroupContent,
	SidebarMenu,
	SidebarMenuButton,
	SidebarMenuItem,
	SidebarMenuSub,
	SidebarMenuSubButton,
	SidebarMenuSubItem,
} from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";
import type { Ticket } from "@/types";

const ticketViews: Array<{
	icon: typeof InboxIcon;
	label: string;
	view: Exclude<SidebarView, "overview">;
}> = [
	{ icon: InboxIcon, label: "All tickets", view: "all" },
	{ icon: ClipboardListIcon, label: "Assigned", view: "assigned" },
	{ icon: AlertTriangleIcon, label: "High priority", view: "high" },
	{ icon: TicketIcon, label: "Pending approval", view: "pending" },
];

export function AppSidebar({
	activeView,
	counts,
	loading = false,
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
	loading?: boolean;
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
	const [commandOpen, setCommandOpen] = useState(false);
	const [commandQuery, setCommandQuery] = useState(search);
	const ticketsOpen = activeView !== "overview";

	useEffect(() => {
		const onKeyDown = (event: KeyboardEvent) => {
			if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
				event.preventDefault();
				setCommandOpen((open) => !open);
			}
		};

		window.addEventListener("keydown", onKeyDown);
		return () => window.removeEventListener("keydown", onKeyDown);
	}, []);

	useEffect(() => {
		if (commandOpen) {
			setCommandQuery(search);
		}
	}, [commandOpen, search]);

	const matchingTickets = useMemo(() => {
		if (loading) {
			return [];
		}

		const query = commandQuery.trim().toLowerCase();
		if (!query) {
			return tickets.slice(0, 7);
		}

		return tickets
			.filter((ticket) =>
				[
					ticket.title,
					ticket.customer,
					ticket.priority,
					ticket.status,
					String(ticket.id),
				].some((value) => value.toLowerCase().includes(query)),
			)
			.slice(0, 8);
	}, [commandQuery, loading, tickets]);

	const navigate = (view: SidebarView) => {
		onNavigate(view);
		setCommandOpen(false);
	};

	const selectTicket = (ticketId: number) => {
		onSelectTicket(ticketId);
		setCommandOpen(false);
	};

	const applySearch = () => {
		setSearch(commandQuery.trim());
		onNavigate("all");
		setCommandOpen(false);
	};

	return (
		<>
			<Sidebar
				className={cn(
					"*:data-[slot=sidebar-inner]:bg-sidebar",
					"**:data-[slot=sidebar-menu-button]:[&>span]:text-sidebar-foreground/75"
				)}
				collapsible="icon"
				variant="sidebar"
			>
				<SidebarContent className="pt-3">
					<SidebarGroup>
						<SidebarGroupContent>
							<button
								aria-label="Search tickets"
								className="mx-2 flex h-10 w-[calc(100%-1rem)] items-center gap-2 rounded-lg border border-input bg-input/30 px-3 text-left text-muted-foreground transition hover:bg-muted hover:text-foreground group-data-[collapsible=icon]:size-8 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0"
								onClick={() => setCommandOpen(true)}
								type="button"
							>
								<SearchIcon className="size-3.5 shrink-0" />
								<span className="min-w-0 flex-1 truncate group-data-[collapsible=icon]:hidden">
									{search ? `Search: ${search}` : "Search tickets"}
								</span>
								<span className="flex items-center gap-1 group-data-[collapsible=icon]:hidden">
									<Kbd>⌘</Kbd>
									<Kbd>K</Kbd>
								</span>
							</button>
						</SidebarGroupContent>
					</SidebarGroup>

					<SidebarGroup>
						<SidebarGroupContent>
							<SidebarMenu className="gap-1.5">
								<SidebarMenuItem>
									<SidebarMenuButton
										className="cursor-pointer"
										isActive={activeView === "overview"}
										onClick={() => onNavigate("overview")}
									>
										<LayoutDashboardIcon />
										<span>Overview</span>
									</SidebarMenuButton>
								</SidebarMenuItem>
								<Collapsible className="group/collapsible" defaultOpen={ticketsOpen}>
									<SidebarMenuItem>
										<CollapsibleTrigger asChild>
											<SidebarMenuButton className="cursor-pointer" isActive={ticketsOpen}>
												<TicketIcon />
												<span>Tickets</span>
												<ChevronDownIcon className="ml-auto transition-transform group-data-[state=open]/collapsible:rotate-180" />
											</SidebarMenuButton>
										</CollapsibleTrigger>
										<CollapsibleContent>
											<SidebarMenuSub className="mt-1 gap-1 border-l">
												{ticketViews.map((item) => {
													const Icon = item.icon;
													return (
														<SidebarMenuSubItem key={item.view}>
															<SidebarMenuSubButton
																isActive={activeView === item.view}
																onClick={() => onNavigate(item.view)}
																className="cursor-pointer gap-2"
															>
																<Icon />
																<span>{item.label}</span>
																{loading ? (
																	<Skeleton className="ml-auto h-4 w-5" />
																) : (
																	<span className="ml-auto text-xs font-medium tabular-nums text-sidebar-foreground">
																		{counts[item.view]}
																	</span>
																)}
															</SidebarMenuSubButton>
														</SidebarMenuSubItem>
													);
												})}
											</SidebarMenuSub>
										</CollapsibleContent>
									</SidebarMenuItem>
								</Collapsible>
							</SidebarMenu>
						</SidebarGroupContent>
					</SidebarGroup>
				</SidebarContent>
				<SidebarFooter className="border-t p-2">
					<NavUser onLogout={onLogout} user={profile} />
				</SidebarFooter>
			</Sidebar>

			<CommandDialog
				description="Search tickets and navigate the service desk."
				onOpenChange={setCommandOpen}
				open={commandOpen}
				title="Service desk command search"
			>
				<Command>
					<CommandInput
						onValueChange={setCommandQuery}
						placeholder="Search tickets or pages..."
						value={commandQuery}
					/>
					<CommandList>
						<CommandEmpty>{loading ? "Loading tickets..." : "No results found."}</CommandEmpty>
						<CommandGroup heading="Pages">
							<CommandItem onSelect={() => navigate("overview")} value="overview dashboard">
								<LayoutDashboardIcon />
								Overview
								<CommandShortcut>⌘1</CommandShortcut>
							</CommandItem>
							{ticketViews.map((item) => {
								const Icon = item.icon;
								return (
									<CommandItem
										key={item.view}
										onSelect={() => navigate(item.view)}
										value={`${item.label} ${item.view}`}
									>
										<Icon />
										{item.label}
										<CommandShortcut>{loading ? "..." : counts[item.view]}</CommandShortcut>
									</CommandItem>
								);
							})}
						</CommandGroup>
						<CommandSeparator />
						<CommandGroup heading="Tickets">
							{loading
								? Array.from({ length: 4 }).map((_, index) => (
									<CommandItem disabled key={index} value={`loading-ticket-${index}`}>
										<span className="grid min-w-0 flex-1 gap-1.5">
											<Skeleton className="h-4 w-48" />
											<Skeleton className="h-3 w-32" />
										</span>
									</CommandItem>
								))
								: matchingTickets.map((ticket) => (
								<CommandItem
									key={ticket.id}
									onSelect={() => selectTicket(ticket.id)}
									value={`${ticket.id} ${ticket.title} ${ticket.customer} ${ticket.priority} ${ticket.status}`}
								>
									<span className="grid min-w-0 flex-1">
										<span className="truncate">{ticket.title}</span>
										<span className="truncate text-xs text-muted-foreground">
											#{ticket.id} · {ticket.customer}
										</span>
									</span>
									<span className="flex items-center gap-1">
										<StatusLabel label={ticket.priority} />
										<StatusLabel label={ticket.status} />
									</span>
								</CommandItem>
							))}
						</CommandGroup>
						{commandQuery.trim() ? (
							<>
								<CommandSeparator />
								<CommandGroup heading="Search">
									<CommandItem onSelect={applySearch} value={`apply search ${commandQuery}`}>
										<SearchIcon />
										Apply ticket filter: “{commandQuery.trim()}”
									</CommandItem>
								</CommandGroup>
							</>
						) : null}
					</CommandList>
				</Command>
			</CommandDialog>
		</>
	);
}
