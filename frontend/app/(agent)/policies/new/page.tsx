"use client";

import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { CheckCircle, Loader2, ShieldCheck } from "lucide-react";
import { useAgentStore } from "@/store/agent";
import { useAuthStore } from "@/store/auth";
import { api } from "@/lib/api";

// ── Zod schema ──────────────────────────────────────────────────────────────
const kycSchema = z.object({
  full_name:            z.string().min(2, "Name required"),
  phone:                z.string().regex(/^[6-9]\d{9}$/, "Valid 10-digit mobile required"),
  aadhaar_number:       z.string().length(12, "Aadhaar must be 12 digits").regex(/^\d+$/),
  date_of_birth:        z.string().min(1, "Date of birth required"),
  district:             z.string().min(1, "District required"),
  state:                z.string().min(1, "State required"),
  occupation:           z.string().min(1, "Occupation required"),
  annual_income:        z.number({ coerce: true }).positive("Income must be positive"),
  pre_existing_conditions: z.array(z.string()).optional(),
});
type KycFormData = z.infer<typeof kycSchema>;

interface Product { id: string; name: string; premium_annual: number; coverage_amount: number; description: string }
interface RiskScore { score: number; risk_level: string; recommended_products: string[]; explanation: string }
interface RazorpayOptions { key: string; amount: number; currency: string; order_id: string; name: string; description: string; handler: (resp: { razorpay_payment_id: string; razorpay_order_id: string; razorpay_signature: string }) => void; prefill: { name: string; contact: string } }
declare global { interface Window { Razorpay: new (opts: RazorpayOptions) => { open(): void } } }

const STEPS = ["kyc", "riskScore", "planSelection", "payment"] as const;

// ── Step indicator ───────────────────────────────────────────────────────────
function StepIndicator({ current }: { current: number }) {
  const t = useTranslations("wizard.steps");
  return (
    <ol className="flex items-center mb-8">
      {STEPS.map((key, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <li key={key} className="flex-1 flex items-center">
            <div className="flex flex-col items-center w-full">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold border-2 ${
                  done   ? "bg-primary-600 border-primary-600 text-white" :
                  active ? "border-primary-600 text-primary-600" :
                           "border-gray-300 text-gray-400"
                }`}
              >
                {done ? <CheckCircle className="h-4 w-4" /> : i + 1}
              </div>
              <span className={`text-xs mt-1 ${active ? "text-primary-600 font-medium" : "text-gray-400"}`}>
                {t(key)}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={`h-0.5 flex-1 mx-2 rounded ${done ? "bg-primary-600" : "bg-gray-200"}`} />
            )}
          </li>
        );
      })}
    </ol>
  );
}

// ── Step 1: KYC Form ─────────────────────────────────────────────────────────
function StepKyc({ onNext }: { onNext: (data: KycFormData) => void }) {
  const t = useTranslations("wizard.kyc");
  const { register, handleSubmit, formState: { errors } } = useForm<KycFormData>({
    resolver: zodResolver(kycSchema),
  });

  return (
    <form onSubmit={handleSubmit(onNext)} className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {[
          { name: "full_name",      label: t("fullName"),      type: "text"   },
          { name: "phone",          label: t("phone"),         type: "tel"    },
          { name: "aadhaar_number", label: t("aadhaar"),       type: "text"   },
          { name: "date_of_birth",  label: t("dob"),           type: "date"   },
          { name: "district",       label: t("district"),      type: "text"   },
          { name: "state",          label: t("state"),         type: "text"   },
          { name: "occupation",     label: t("occupation"),    type: "text"   },
          { name: "annual_income",  label: t("annualIncome"),  type: "number" },
        ].map(({ name, label, type }) => (
          <div key={name}>
            <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
            <input
              type={type}
              {...register(name as keyof KycFormData)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-300"
            />
            {errors[name as keyof KycFormData] && (
              <p className="text-xs text-red-500 mt-1">
                {errors[name as keyof KycFormData]?.message as string}
              </p>
            )}
          </div>
        ))}
      </div>
      <button
        type="submit"
        className="w-full bg-primary-600 text-white py-2.5 rounded-lg font-medium hover:bg-primary-700 transition-colors"
      >
        {t("continue")}
      </button>
    </form>
  );
}

// ── Step 2: Risk Score (with ≥2 s loading animation) ─────────────────────────
function StepRiskScore({
  kycData,
  onNext,
}: {
  kycData: KycFormData;
  onNext: (score: RiskScore) => void;
}) {
  const t = useTranslations("wizard.riskScore");
  const agentId = useAuthStore((s) => s.agentId);
  const [minWaitDone, setMinWaitDone] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setMinWaitDone(true), 2000);
    return () => clearTimeout(timer);
  }, []);

  const { data, isSuccess } = useQuery<RiskScore>({
    queryKey: ["risk-score", kycData.phone],
    queryFn: () =>
      api.post<RiskScore>("/api/v1/ai/score-risk", {
        age:                     new Date().getFullYear() - new Date(kycData.date_of_birth).getFullYear(),
        occupation:              kycData.occupation,
        annual_income:           kycData.annual_income,
        district:                kycData.district,
        state:                   kycData.state,
        pre_existing_conditions: kycData.pre_existing_conditions ?? [],
        agent_id:                agentId,
      }),
    staleTime: Infinity,
  });

  const ready = isSuccess && minWaitDone;

  const riskColor: Record<string, string> = {
    LOW:    "text-green-600",
    MEDIUM: "text-yellow-600",
    HIGH:   "text-red-600",
  };

  if (!ready) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-4">
        <Loader2 className="h-12 w-12 text-primary-600 animate-spin" />
        <p className="text-gray-600 font-medium">{t("analyzing")}</p>
        <p className="text-sm text-gray-400">{t("analyzingSubtext")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="bg-gray-50 rounded-xl p-6 text-center">
        <p className="text-sm text-gray-500 mb-1">{t("riskScore")}</p>
        <p className="text-5xl font-bold text-gray-800">{data!.score}</p>
        <p className={`text-lg font-semibold mt-2 ${riskColor[data!.risk_level]}`}>
          {data!.risk_level} {t("risk")}
        </p>
        <p className="text-sm text-gray-500 mt-3 max-w-md mx-auto">{data!.explanation}</p>
      </div>
      <button
        onClick={() => onNext(data!)}
        className="w-full bg-primary-600 text-white py-2.5 rounded-lg font-medium hover:bg-primary-700 transition-colors"
      >
        {t("viewPlans")}
      </button>
    </div>
  );
}

// ── Step 3: Plan selection ────────────────────────────────────────────────────
function StepPlanSelection({
  riskScore,
  onNext,
}: {
  riskScore: RiskScore;
  onNext: (product: Product) => void;
}) {
  const t = useTranslations("wizard.plan");
  const [selected, setSelected] = useState<string | null>(null);

  const { data: products = [], isLoading } = useQuery<Product[]>({
    queryKey: ["products"],
    queryFn: () => api.get<Product[]>("/api/v1/policies/products"),
    staleTime: 5 * 60 * 1000,
  });

  const recommended = riskScore.recommended_products;

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-500">{t("subtitle")}</p>
      <div className="grid gap-3">
        {isLoading
          ? Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-24 bg-gray-200 rounded-xl animate-pulse" />
            ))
          : products.map((p) => {
              const isRecommended = recommended.includes(p.id);
              const isSelected = selected === p.id;
              return (
                <button
                  key={p.id}
                  onClick={() => setSelected(p.id)}
                  className={`w-full text-left p-4 rounded-xl border-2 transition-colors ${
                    isSelected
                      ? "border-primary-600 bg-primary-50"
                      : "border-gray-200 hover:border-primary-300"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <ShieldCheck className={`h-4 w-4 ${isSelected ? "text-primary-600" : "text-gray-400"}`} />
                        <span className="font-medium text-gray-800">{p.name}</span>
                        {isRecommended && (
                          <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">
                            {t("recommended")}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-gray-500 mt-1">{p.description}</p>
                    </div>
                    <div className="text-right ml-4">
                      <p className="font-bold text-gray-800">₹{p.premium_annual.toLocaleString("en-IN")}</p>
                      <p className="text-xs text-gray-400">{t("perYear")}</p>
                      <p className="text-xs text-primary-600 font-medium mt-1">
                        {t("cover")} ₹{(p.coverage_amount / 100000).toFixed(0)}L
                      </p>
                    </div>
                  </div>
                </button>
              );
            })}
      </div>
      <button
        disabled={!selected}
        onClick={() => {
          const p = products.find((p) => p.id === selected);
          if (p) onNext(p);
        }}
        className="w-full bg-primary-600 text-white py-2.5 rounded-lg font-medium hover:bg-primary-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {t("proceed")}
      </button>
    </div>
  );
}

// ── Step 4: Razorpay payment ──────────────────────────────────────────────────
function StepPayment({
  kycData,
  product,
  onSuccess,
}: {
  kycData: KycFormData;
  product: Product;
  onSuccess: () => void;
}) {
  const t = useTranslations("wizard.payment");
  const agentId = useAuthStore((s) => s.agentId);
  const scriptLoaded = useRef(false);

  useEffect(() => {
    if (scriptLoaded.current) return;
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    document.body.appendChild(script);
    scriptLoaded.current = true;
  }, []);

  const createOrder = useMutation({
    mutationFn: () =>
      api.post<{ razorpay_order_id: string; amount: number }>("/api/v1/payments/create-order", {
        product_id:    product.id,
        agent_id:      agentId,
        user_phone:    kycData.phone,
        amount:        product.premium_annual * 100, // paise
      }),
    onSuccess: ({ razorpay_order_id, amount }) => {
      const options: RazorpayOptions = {
        key:         process.env.NEXT_PUBLIC_RAZORPAY_KEY_ID ?? "",
        amount,
        currency:    "INR",
        order_id:    razorpay_order_id,
        name:        "Bima360",
        description: product.name,
        handler: async (response) => {
          await api.post("/api/v1/payments/verify", {
            razorpay_order_id:   response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature:  response.razorpay_signature,
          });
          onSuccess();
        },
        prefill: { name: kycData.full_name, contact: kycData.phone },
      };
      new window.Razorpay(options).open();
    },
  });

  return (
    <div className="space-y-6">
      <div className="bg-gray-50 rounded-xl p-5">
        <h3 className="font-semibold text-gray-800 mb-3">{t("summary")}</h3>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between"><span className="text-gray-500">{t("plan")}</span><span className="font-medium">{product.name}</span></div>
          <div className="flex justify-between"><span className="text-gray-500">{t("customer")}</span><span className="font-medium">{kycData.full_name}</span></div>
          <div className="flex justify-between"><span className="text-gray-500">{t("coverage")}</span><span className="font-medium">₹{(product.coverage_amount / 100000).toFixed(0)}L</span></div>
          <div className="flex justify-between border-t border-gray-200 pt-2 mt-2"><span className="font-semibold text-gray-700">{t("premium")}</span><span className="font-bold text-primary-600">₹{product.premium_annual.toLocaleString("en-IN")}</span></div>
        </div>
      </div>
      <button
        onClick={() => createOrder.mutate()}
        disabled={createOrder.isPending}
        className="w-full bg-primary-600 text-white py-2.5 rounded-lg font-medium hover:bg-primary-700 transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
      >
        {createOrder.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
        {t("payNow")} ₹{product.premium_annual.toLocaleString("en-IN")}
      </button>
    </div>
  );
}

// ── Main wizard page ─────────────────────────────────────────────────────────
export default function NewPolicyPage() {
  const t = useTranslations("wizard");
  const { activeWizardStep: step, setWizardStep } = useAgentStore();
  const [kycData, setKycData] = useState<KycFormData | null>(null);
  const [riskScore, setRiskScore] = useState<RiskScore | null>(null);
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [done, setDone] = useState(false);

  if (done) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
        <CheckCircle className="h-16 w-16 text-green-500" />
        <h2 className="text-xl font-bold text-gray-800">{t("success.title")}</h2>
        <p className="text-gray-500 max-w-sm">{t("success.subtitle")}</p>
        <button
          onClick={() => { setDone(false); setWizardStep(0); setKycData(null); setRiskScore(null); setSelectedProduct(null); }}
          className="mt-4 bg-primary-600 text-white px-6 py-2.5 rounded-lg font-medium hover:bg-primary-700 transition-colors"
        >
          {t("success.newPolicy")}
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      <h2 className="text-lg font-semibold text-gray-800 mb-6">{t("title")}</h2>
      <StepIndicator current={step} />

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        {step === 0 && (
          <StepKyc
            onNext={(data) => { setKycData(data); setWizardStep(1); }}
          />
        )}
        {step === 1 && kycData && (
          <StepRiskScore
            kycData={kycData}
            onNext={(score) => { setRiskScore(score); setWizardStep(2); }}
          />
        )}
        {step === 2 && riskScore && (
          <StepPlanSelection
            riskScore={riskScore}
            onNext={(product) => { setSelectedProduct(product); setWizardStep(3); }}
          />
        )}
        {step === 3 && kycData && selectedProduct && (
          <StepPayment
            kycData={kycData}
            product={selectedProduct}
            onSuccess={() => setDone(true)}
          />
        )}
      </div>
    </div>
  );
}
