"use client";

import { useTranslations } from "next-intl";
import { useAuthStore } from "@/store/auth";

export default function UserLayout({ children }: { children: React.ReactNode }) {
  const t = useTranslations("userPortal");
  const clearSession = useAuthStore((s) => s.clearSession);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <span className="text-lg font-bold text-primary-600">Bima360</span>
        <button
          onClick={clearSession}
          className="text-sm text-gray-500 hover:text-red-600 transition-colors"
        >
          {t("logout")}
        </button>
      </header>
      <main className="max-w-3xl mx-auto px-4 py-8">{children}</main>
    </div>
  );
}
