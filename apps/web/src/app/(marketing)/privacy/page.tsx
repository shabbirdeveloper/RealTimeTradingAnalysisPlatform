export default function PrivacyPage() {
  return (
    <div className="container max-w-2xl py-16">
      <h1 className="text-3xl font-semibold text-foreground">Privacy Policy</h1>
      <div className="mt-6 space-y-4 text-sm leading-relaxed text-muted-foreground">
        <p>We collect the minimum data required to operate your account: email, authentication metadata, and your notification and subscription preferences.</p>
        <p>Market data, generated signals, and backtest results are stored to power your dashboard and are not shared with third parties for advertising purposes.</p>
        <p>We never store broker credentials for Quotex or any other platform — execution is always manual and happens entirely outside this application.</p>
        <p>You may request export or deletion of your account data at any time from Settings.</p>
      </div>
    </div>
  );
}
