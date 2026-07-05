import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Menu, Bell, ChevronDown, Shield, LogOut, User } from 'lucide-react';
import type { User as UserType, Notification } from '@/types';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

interface TopBarProps {
  breadcrumb: string;
  pageTitle: string;
  user: UserType | null;
  onLogout: () => void | Promise<void>;
  onNavigate: (route: string) => void;
  onMobileMenuToggle: () => void;
  notifications: Notification[];
}

export function TopBar({ breadcrumb, pageTitle, user, onLogout, onNavigate, onMobileMenuToggle, notifications }: TopBarProps) {
  const navigate = useNavigate();
  const [showUserMenu, setShowUserMenu] = useState(false);
  const unreadCount = notifications.filter(n => !n.read).length;

  const handleLogout = async () => {
    await onLogout();
    navigate('/signin');
  };

  return (
    <header className="flex items-center justify-between h-14 px-4 lg:px-6 bg-[#000000] border-b border-[#2E2E2E] flex-shrink-0">
      {/* Left */}
      <div className="flex items-center gap-3 min-w-0">
        <button
          onClick={onMobileMenuToggle}
          className="lg:hidden w-9 h-9 flex items-center justify-center rounded-lg text-[#B8B8B8] hover:text-white hover:bg-[#1E1E1E] transition-colors"
        >
          <Menu className="w-5 h-5" />
        </button>
        <div className="min-w-0">
          <p className="text-xs text-[#8C8C8C] truncate hidden sm:block">{breadcrumb}</p>
          <h1 className="text-sm font-semibold text-white lg:hidden">{pageTitle}</h1>
        </div>
      </div>

      {/* Right */}
      <div className="flex items-center gap-2">
        {/* Notifications */}
        <button className="relative w-9 h-9 flex items-center justify-center rounded-lg text-[#B8B8B8] hover:text-white hover:bg-[#1E1E1E] transition-colors">
          <Bell className="w-5 h-5" />
          {unreadCount > 0 && (
            <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-[#F97066] rounded-full" />
          )}
        </button>

        {/* User Avatar */}
        <DropdownMenu open={showUserMenu} onOpenChange={setShowUserMenu}>
          <DropdownMenuTrigger asChild>
            <button className="flex items-center gap-2 ml-2 rounded-lg hover:bg-[#1E1E1E] transition-colors px-2 py-1.5">
              <div className="w-8 h-8 rounded-full bg-[#c16e43] flex items-center justify-center text-white text-xs font-semibold">
                {user?.name?.split(' ').map(n => n[0]).join('') || 'U'}
              </div>
              <ChevronDown className="w-4 h-4 text-[#8C8C8C] hidden sm:block" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="end"
            className="w-[200px] bg-[#151515] border-[#2E2E2E] text-white"
          >
            <div className="px-3 py-2">
              <p className="text-sm font-semibold">{user?.name}</p>
              <p className="text-xs text-[#B8B8B8]">{user?.email}</p>
              <span className="inline-block mt-1.5 px-2 py-0.5 bg-[#c16e43]/10 text-[#E4E4E7] text-[10px] font-medium uppercase tracking-wider rounded-full">
                {user?.role}
              </span>
            </div>
            <DropdownMenuSeparator className="bg-[#2E2E2E]" />
            {user?.role === 'Admin' && (
              <DropdownMenuItem
                onClick={() => { onNavigate('/app/admin-panel'); setShowUserMenu(false); }}
                className="text-[#B8B8B8] focus:text-white focus:bg-[#1E1E1E] cursor-pointer"
              >
                <Shield className="w-4 h-4 mr-2" />
                Admin Panel
              </DropdownMenuItem>
            )}
            <DropdownMenuItem
              className="text-[#B8B8B8] focus:text-white focus:bg-[#1E1E1E] cursor-pointer"
            >
              <User className="w-4 h-4 mr-2" />
              Profile
            </DropdownMenuItem>
            <DropdownMenuSeparator className="bg-[#2E2E2E]" />
            <DropdownMenuItem
              onClick={handleLogout}
              className="text-[#F97066] focus:text-[#F97066] focus:bg-[#F97066]/10 cursor-pointer"
            >
              <LogOut className="w-4 h-4 mr-2" />
              Logout
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
