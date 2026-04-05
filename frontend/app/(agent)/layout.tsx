"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import {
  LayoutDashboard,
  Users,
  FilePlus,
  FileText,
  Wallet,
  LogOut,
  Globe,
} from "lucide-react";
import { useAuthStore } from "@/store/auth";
import { useAgentStore } from "@/store/agent";

const navItems = [
  { href: "/agent/dashboard", icon: LayoutDashboard, key: "dashboard" },
  { href: "/agent/clients",   icon: Users,           key: "clients"   },
  { href: "/agent/policies/new", icon: FilePlus,      key: "newPolicy" },
  { href: "/agent/claims",    icon: FileText,        key: "claims"    },
  { href: "/agent/earnings",  icon: Wallet,          key: "earnings"  },
];

export default function AgentLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const t = useTranslations("nav");
  const pathname = usePathname();
  const router = useRouter();
  const clearSession = useAuthStore((s) => s.clearSession);
  const agentName = useAuthStore((s) => s.agentName);
  const { language, setLanguage } = useAgentStore();

  function handleLogout() {
    clearSession();
    router.push("/auth/login");
  }

  function toggleLanguage() {
    const next = language === "en" ? "hi" : "en";
    setLanguage(next);
    document.cookie = `locale=${next}; path=/; max-age=31536000`;
    router.refresh();
  }

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col">
        <div className="px-6 py-5 border-b border-gray-200">
          <span className="text-xl font-bold text-primary-600">Bima360</span>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1">
          {navItems.map(({ href, icon: Icon, key }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  active
                    ? "bg-primary-50 text-primary-700"
                    : "text-gray-600 hover:bg-gray-100"
                }`}
              >
                <Icon className="h-4 w-4" />
                {t(key)}
              </Link>
            );
          })}
        </nav>

        <div className="px-3 pb-4 space-y-1 border-t border-gray-200 pt-4">
          <button
            onClick={toggleLanguage}
            className="flex items-center gap-3 w-full px-3 py-2 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-100 transition-colors"
          >
            <Globe className="h-4 w-4" />
            {language === "en" ? "हिन्दी" : "English"}
          </button>
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 w-full px-3 py-2 rounded-lg text-sm font-medium text-red-600 hover:bg-red-50 transition-colors"
          >
            <LogOut className="h-4 w-4" />
            {t("logout")}
          </button>
        </div>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar */}
        <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
          <h1 className="text-sm text-gray-500">
            {t("welcome")},{" "}
            <span className="font-semibold text-gray-800">{agentName}</span>
          </h1>
        </header>

        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
