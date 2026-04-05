"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { Users, ShieldCheck, AlertCircle, IndianRupee } from "lucide-react";
import { useAuthStore } from "@/store/auth";
import { api } from "@/lib/api";

interface DashboardStats {
  total_clients: number;
  active_policies: number;
  pending_claims: number;
  commission_earned: number;
}

function StatCard({
  label,
  value,
  icon: Icon,
  color,
  loading,
}: {
  label: string;
  value: string | number;
  icon: React.ElementType;
  color: string;
  loading: boolean;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 flex items-center gap-4">
      <div className={`p-3 rounded-lg ${color}`}>
        <Icon className="h-5 w-5 text-white" />
      </div>
      <div>
        <p className="text-sm text-gray-500">{label}</p>
        {loading ? (
          <div className="h-6 w-16 bg-gray-200 rounded animate-pulse mt-1" />
        ) : (
          <p className="text-2xl font-bold text-gray-800">{value}</p>
        )}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const t = useTranslations("dashboard");
  const agentId = useAuthStore((s) => s.agentId);

  const { data, isLoading } = useQuery<DashboardStats>({
    queryKey: ["dashboard-stats", agentId],
    queryFn: () => api.get<DashboardStats>(`/api/v1/agents/${agentId}/stats`),
    enabled: Boolean(agentId),
  });

  const stats = [
    {
      key: "totalClients",
      value: data?.total_clients ?? 0,
      icon: Users,
      color: "bg-blue-500",
    },
    {
      key: "activePolicies",
      value: data?.active_policies ?? 0,
      icon: ShieldCheck,
      color: "bg-green-500",
    },
    {
      key: "pendingClaims",
      value: data?.pending_claims ?? 0,
      icon: AlertCircle,
      color: "bg-yellow-500",
    },
    {
      key: "commissionEarned",
      value: `₹${(data?.commission_earned ?? 0).toLocaleString("en-IN")}`,
      icon: IndianRupee,
      color: "bg-saffron-500",
    },
  ];

  return (
    <div>
      <h2 className="text-lg font-semibold text-gray-800 mb-5">
        {t("title")}
      </h2>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((s) => (
          <StatCard
            key={s.key}
            label={t(s.key)}
            value={s.value}
            icon={s.icon}
            color={s.color}
            loading={isLoading}
          />
        ))}
      </div>
    </div>
  );
}
