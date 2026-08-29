import Link from "next/link";
import { Logo } from "@/components/layout/logo";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-4 py-16">
      <div className="bg-grid pointer-events-none absolute inset-0" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[420px] bg-[radial-gradient(ellipse_640px_360px_at_50%_-10%,hsl(var(--primary)/0.14),transparent_65%)]" />
      <Link href="/" className="relative mb-8"><Logo /></Link>
      <div className="relative w-full max-w-sm">{children}</div>
    </div>
  );
}
