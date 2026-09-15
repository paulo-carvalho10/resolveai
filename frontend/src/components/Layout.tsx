import {
  BookOpen,
  LayoutDashboard,
  LifeBuoy,
  LogOut,
  Moon,
  Plus,
  Settings,
  Sun,
  Ticket as TicketIcon,
} from "lucide-react";
import { NavLink, Outlet } from "react-router";

import { useAuth } from "../auth/AuthProvider";
import { USER_ROLE } from "../lib/labels";
import { useTheme } from "../theme/ThemeProvider";

function navClasses({ isActive }: { isActive: boolean }): string {
  return [
    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
    isActive ? "bg-brand-soft text-brand" : "text-text-muted hover:bg-surface-muted hover:text-text",
  ].join(" ");
}

export function Layout() {
  const { user, isStaff, isAdmin, logout } = useAuth();
  const { theme, toggle } = useTheme();

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[240px_1fr]">
      <aside className="border-b border-border bg-surface px-4 py-4 lg:sticky lg:top-0 lg:h-dvh lg:border-r lg:border-b-0">
        <div className="flex items-center gap-2 px-2 pb-6">
          <LifeBuoy aria-hidden className="size-5 text-brand" />
          <span className="text-base font-semibold tracking-tight">ResolveAI</span>
        </div>

        <nav className="flex flex-wrap gap-1 lg:flex-col">
          {isStaff && (
            <NavLink to="/" end className={navClasses}>
              <LayoutDashboard aria-hidden className="size-4" />
              Dashboard
            </NavLink>
          )}
          <NavLink to="/chamados" className={navClasses}>
            <TicketIcon aria-hidden className="size-4" />
            {isStaff ? "Chamados" : "Meus chamados"}
          </NavLink>
          <NavLink to="/chamados/novo" className={navClasses}>
            <Plus aria-hidden className="size-4" />
            Novo chamado
          </NavLink>
          <NavLink to="/base-de-conhecimento" className={navClasses}>
            <BookOpen aria-hidden className="size-4" />
            Base de conhecimento
          </NavLink>
          {isAdmin && (
            <NavLink to="/administracao" className={navClasses}>
              <Settings aria-hidden className="size-4" />
              Administração
            </NavLink>
          )}
        </nav>

        <div className="mt-6 border-t border-border pt-4 lg:absolute lg:bottom-4 lg:w-[208px]">
          <div className="px-2 pb-3">
            <p className="truncate text-sm font-medium text-text">{user?.full_name}</p>
            <p className="truncate text-xs text-text-muted">
              {user ? USER_ROLE[user.role] : ""}
            </p>
          </div>
          <div className="flex gap-1">
            <button type="button" className="btn-ghost flex-1" onClick={toggle}>
              {theme === "dark" ? (
                <Sun aria-hidden className="size-4" />
              ) : (
                <Moon aria-hidden className="size-4" />
              )}
              {theme === "dark" ? "Tema claro" : "Tema escuro"}
            </button>
            <button type="button" className="btn-ghost" onClick={logout} aria-label="Sair">
              <LogOut aria-hidden className="size-4" />
            </button>
          </div>
        </div>
      </aside>

      <main className="min-w-0 px-4 py-6 sm:px-6 lg:px-8">
        <Outlet />
      </main>
    </div>
  );
}

export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-text">{title}</h1>
        {description && <p className="mt-1 text-sm text-text-muted">{description}</p>}
      </div>
      {action}
    </header>
  );
}
