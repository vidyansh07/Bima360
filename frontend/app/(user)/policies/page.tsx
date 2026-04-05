"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { ShieldCheck, ExternalLink } from "lucide-react";
import { api } from "@/lib/api";

interface Policy {
  id: string;
  product_name: string;
  status: string;
  start_date: string;
  end_date: string;
  premium_paid: number;
  coverage_amount: number;
  fabric_tx_id: string | null;
}

const statusClasses: Record<string, string> = {
  active:    "bg-green-100 text-green-700",
  expired:   "bg-gray-100 text-gray-600",
  cancelled: "bg-red-100 text-red-700",
  pending:   "bg-yellow-100 text-yellow-700",
};

export default function UserPoliciesPage() {
  const t = useTranslations("userPortal.policies");

  const { data: policies = [], isLoading } = useQuery<Policy[]>({
    queryKey: ["user-policies"],
    queryFn: () => api.get<Policy[]>("/api/v1/policies/me"),
  });

  return (
    <div>
      <h2 className="text-lg font-semibold text-gray-800 mb-5">{t("title")}</h2>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-28 bg-white rounded-xl border border-gray-200 animate-pulse" />
          ))}
        </div>
      ) : policies.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <ShieldCheck className="h-12 w-12 mx-auto mb-3 opacity-40" />
          <p>{t("noPolicies")}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {policies.map((p) => (
            <div key={p.id} className="bg-white rounded-xl border border-gray-200 p-5">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <ShieldCheck className="h-8 w-8 text-primary-600 shrink-0" />
                  <div>
                    <p className="font-semibold text-gray-800">{p.product_name}</p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {new Date(p.start_date).toLocaleDateString("en-IN")} →{" "}
                      {new Date(p.end_date).toLocaleDateString("en-IN")}
                    </p>
                  </div>
                </div>
                <span
                  className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                    statusClasses[p.status] ?? "bg-gray-100 text-gray-600"
                  }`}
                >
                  {p.status}
                </span>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                <div>
                  <p className="text-gray-400 text-xs">{t("premium")}</p>
                  <p className="font-medium text-gray-700">₹{p.premium_paid.toLocaleString("en-IN")}</p>
                </div>
                <div>
                  <p className="text-gray-400 text-xs">{t("coverage")}</p>
                  <p className="font-medium text-gray-700">₹{(p.coverage_amount / 100000).toFixed(0)}L</p>
                </div>
              </div>

              {p.fabric_tx_id && (
                <div className="mt-3 pt-3 border-t border-gray-100 flex items-center gap-2">
                  <ExternalLink className="h-3 w-3 text-gray-400" />
                  <span className="text-xs text-gray-400">{t("blockchainTx")}:</span>
                  <span className="text-xs font-mono text-gray-600 truncate max-w-xs">
                    {p.fabric_tx_id}
                  </span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
