"use client";

import {
	Avatar,
	AvatarFallback,
} from "@/components/ui/avatar";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuGroup,
	DropdownMenuItem,
	DropdownMenuLabel,
	DropdownMenuSeparator,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { LogOutIcon, ShieldCheckIcon } from "lucide-react";

export function NavUser({
	onLogout,
	user,
}: {
	onLogout: () => void;
	user: {
		email: string;
		name: string;
		role: string;
	};
}) {
	const fallback = user.name.trim().slice(0, 1).toUpperCase() || "T";

	return (
		<DropdownMenu>
			<DropdownMenuTrigger asChild>
				<button
					className="flex w-full items-center gap-2 rounded-lg p-2 text-left transition hover:bg-muted"
					type="button"
				>
					<Avatar className="size-8">
						<AvatarFallback>{fallback}</AvatarFallback>
					</Avatar>
					<span className="grid min-w-0 flex-1 leading-tight group-data-[collapsible=icon]:hidden">
						<span className="truncate text-sm font-medium">{user.name}</span>
						<span className="truncate text-xs text-muted-foreground">{user.email}</span>
					</span>
				</button>
			</DropdownMenuTrigger>
			<DropdownMenuContent align="end" className="w-60">
				<DropdownMenuLabel className="flex items-center gap-3">
					<Avatar className="size-9">
						<AvatarFallback>{fallback}</AvatarFallback>
					</Avatar>
					<span className="grid min-w-0">
						<span className="truncate font-medium text-foreground">{user.name}</span>
						<span className="truncate text-xs text-muted-foreground">{user.role}</span>
					</span>
				</DropdownMenuLabel>
				<DropdownMenuSeparator />
				<DropdownMenuGroup>
					<DropdownMenuItem disabled>
						<ShieldCheckIcon />
						Human approval active
					</DropdownMenuItem>
				</DropdownMenuGroup>
				<DropdownMenuSeparator />
				<DropdownMenuGroup>
					<DropdownMenuItem
						className="w-full cursor-pointer"
						onClick={onLogout}
						variant="destructive"
					>
						<LogOutIcon />
						Sign out
					</DropdownMenuItem>
				</DropdownMenuGroup>
			</DropdownMenuContent>
		</DropdownMenu>
	);
}
