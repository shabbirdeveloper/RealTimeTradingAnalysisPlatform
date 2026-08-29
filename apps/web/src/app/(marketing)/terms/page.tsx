export default function TermsPage() {
  return (
    <div className="container max-w-2xl py-16">
      <h1 className="text-3xl font-semibold text-foreground">Terms of Service</h1>
      <div className="mt-6 space-y-4 text-sm leading-relaxed text-muted-foreground">
        <p>By using NorthFXTrade you agree that all signals are informational only and require manual execution on a platform of your choosing.</p>
        <p>You agree not to use this software to automate, script, or otherwise programmatically place trades on any broker, including Quotex, based on its output.</p>
        <p>Subscriptions are billed per the plan selected at checkout and may be cancelled at any time from Billing settings.</p>
        <p>We reserve the right to suspend accounts that attempt to reverse-engineer or automate trade execution against these terms.</p>
      </div>
    </div>
  );
}
