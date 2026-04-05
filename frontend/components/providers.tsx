"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { Amplify } from "aws-amplify";
import { NextIntlClientProvider } from "next-intl";
import { type ReactNode, useEffect } from "react";
import { getQueryClient } from "@/lib/query-client";

Amplify.configure(
  {
    Auth: {
      Cognito: {
        userPoolId: process.env.NEXT_PUBLIC_COGNITO_AGENT_POOL_ID ?? "",
        userPoolClientId:
          process.env.NEXT_PUBLIC_COGNITO_AGENT_CLIENT_ID ?? "",
      },
    },
  },
  { ssr: true }
);

interface ProvidersProps {
  children: ReactNode;
  locale: string;
  messages: Record<string, unknown>;
}

export function Providers({ children, locale, messages }: ProvidersProps) {
  const queryClient = getQueryClient();

  return (
    <NextIntlClientProvider locale={locale} messages={messages}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </NextIntlClientProvider>
  );
}
