"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { Search, UserPlus, Phone } from "lucide-react";
import Link from "next/link";
import { useAuthStore } from "@/store/auth";
import { api } from "@/lib/api";

interface Client {
  id: string;
  full_name: string;
  phone: string;
  district: string;
  state: string;
  kyc_status: string;
  total_policies: number;
}

export default function ClientsPage() {
  const t = useTranslations("clients");
  const agentId = useAuthStore((s) => s.agentId);
  const [search, setSearch] = useState("");

  const { data: clients = [], isLoading } = useQuery<Client[]>({
    queryKey: ["clients", agentId, search],
    queryFn: () =>
      api.get<Client[]>(
        `/api/v1/policies/my-clients?search=${encodeURIComponent(search)}`
      ),
    enabled: Boolean(agentId),
  });

  const kycBadge: Record<string, string> = {
    verified: "bg-green-100 text-green-700",
    pending:  "bg-yellow-100 text-yellow-700",
    rejected: "bg-red-100 text-red-700",
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <h2 className="text-lg font-semibold text-gray-800">{t("title")}</h2>
        <Link
          href="/agent/policies/new"
          className="flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-primary-700 transition-colors"
        >
          <UserPlus className="h-4 w-4" />
          {t("addClient")}
        </Link>
      </div>

      {/* Search */}
      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
        <input
          type="text"
          placeholder={t("searchPlaceholder")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-300"
        />
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              {["name", "phone", "location", "kyc", "policies"].map((col) => (
                <th
                  key={col}
                  className="px-4 py-3 text-left font-medium text-gray-600"
                >
                  {t(`col.${col}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading
              ? Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} className="border-b border-gray-100">
                    {Array.from({ length: 5 }).map((__, j) => (
                      <td key={j} className="px-4 py-3">
                        <div className="h-4 bg-gray-200 rounded animate-pulse" />
                      </td>
                    ))}
                  </tr>
                ))
              : clients.map((c) => (
                  <tr
                    key={c.id}
                    className="border-b border-gray-100 hover:bg-gray-50"
                  >
                    <td className="px-4 py-3 font-medium text-gray-800">
                      {c.full_name}
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      <a
                        href={`tel:${c.phone}`}
                        className="flex items-center gap-1 hover:text-primary-600"
                      >
                        <Phone className="h-3 w-3" />
                        {c.phone}
                      </a>
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {c.district}, {c.state}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                          kycBadge[c.kyc_status] ?? "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {c.kyc_status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {c.total_policies}
                    </td>
                  </tr>
                ))}
          </tbody>
        </table>
        {!isLoading && clients.length === 0 && (
          <p className="text-center text-gray-400 py-10 text-sm">
            {t("noClients")}
          </p>
        )}
      </div>
    </div>
  );
}
