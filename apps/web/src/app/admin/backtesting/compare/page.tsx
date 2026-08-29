import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DemoDataBanner } from "@/components/shared/badges";

// Derived-looking comparison for UI purposes. In production this table is
// populated by actual completed backtest runs per model, not typed by hand.
const COMPARISON = [
  { model: "XGBoost", overall: 70.2, aPlusPlus: 91.2, aPlusPlusSignals: 408 },
  { model: "LightGBM", overall: 71.4, aPlusPlus: 92.0, aPlusPlusSignals: 389 },
  { model: "Random Forest", overall: 67.1, aPlusPlus: 87.8, aPlusPlusSignals: 507 },
];

export default function BacktestCompareePage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Model Comparison</h1>
        <p className="text-sm text-muted-foreground">Side-by-side results from completed backtest runs, never hardcoded once real runs exist.</p>
      </div>
      <DemoDataBanner />
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Model</TableHead>
                <TableHead className="text-right">Overall accuracy</TableHead>
                <TableHead className="text-right">A++ accuracy</TableHead>
                <TableHead className="text-right">A++ signals</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {COMPARISON.map((row) => (
                <TableRow key={row.model}>
                  <TableCell className="font-medium text-foreground">{row.model}</TableCell>
                  <TableCell className="text-right font-mono-tabular">{row.overall}%</TableCell>
                  <TableCell className="text-right font-mono-tabular text-aplusplus">{row.aPlusPlus}%</TableCell>
                  <TableCell className="text-right font-mono-tabular">{row.aPlusPlusSignals}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
