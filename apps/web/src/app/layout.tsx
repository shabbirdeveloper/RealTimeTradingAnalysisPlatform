import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { PwaProvider } from "@/components/shared/pwa-provider";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: {
    default: "NorthFXTrade — Algorithmic Market Analysis",
    template: "%s — NorthFXTrade",
  },
  description:
    "Institutional-grade market analysis and informational trading signals for XAU/USD, EUR/USD, GBP/USD, BTC/USD and ETH/USD. Manual execution only.",
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = {
  themeColor: "#0a0e14",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`} suppressHydrationWarning>
      <body className="dark min-h-screen bg-background font-sans text-foreground">
        {children}
        <PwaProvider />
      </body>
    </html>
  );
}
