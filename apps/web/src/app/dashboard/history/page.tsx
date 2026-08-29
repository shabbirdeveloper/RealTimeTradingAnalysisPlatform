"use client";
import { useMemo, useState } from "react";
import { HISTORICAL_SIGNALS } from "@/data/history";
import { ASSET_LIST, ASSET_CONFIGS } from "@/data/assets";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { DirectionBadge, GradeBadge, DemoDataBanner } from "@/components/shared/badges";
import { formatDateTimeUTC, formatPercent, formatPrice } from "@/lib/utils";
import type { AssetSymbol, Direction, SignalGrade } from "@/types";

const ALL = "ALL";

export default function HistoryPage() {
  const [asset, setAsset] = useState<string>(ALL);
  const [direction, setDirection] = useState<string>(ALL);
  const [grade, setGrade] = useState<string>(ALL);
  const [result, setResult] = useState<string>(ALL);
  const [expiry, setExpiry] = useState<string>(ALL);
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    return HISTORICAL_SIGNALS.filter((s) => {
      if (asset !== ALL && s.asset !== asset) return false;
      if (direction !== ALL && s.direction !== direction) return false;
      if (grade !== ALL && s.grade !== grade) return false;
      if (result !== ALL && s.result !== result) return false;
      if (expiry !== ALL && String(s.expiryMinutes) !== expiry) return false;
      if (search && !s.id.toLowerCase().includes(search.toLowerCase()) && !ASSET_CONFIGS[s.asset].displayName.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    }).slice(0, 200);
  }, [asset, direction, grade, result, expiry, search]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-foreground">Signal History</h1>
        <p className="text-sm text-muted-foreground">{filtered.length} of {HISTORICAL_SIGNALS.length} records shown.</p>
      </div>

      <DemoDataBanner />

      <Card>
        <CardContent className="flex flex-wrap gap-3 p-4">
          <Input placeholder="Search…" value={search} onChange={(e) => setSearch(e.target.value)} className="w-40" />
          <FilterSelect label="Asset" value={asset} onChange={setAsset} options={[ALL, ...ASSET_LIST]} />
          <FilterSelect label="Direction" value={direction} onChange={setDirection} options={[ALL, "CALL", "PUT", "NO_TRADE"]} />
          <FilterSelect label="Grade" value={grade} onChange={setGrade} options={[ALL, "A++", "A+", "A", "B"]} />
          <FilterSelect label="Result" value={result} onChange={setResult} options={[ALL, "WON", "LOST", "DRAW"]} />
          <FilterSelect label="Expiry" value={expiry} onChange={setExpiry} options={[ALL, "15", "30", "60"]} />
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Timestamp</TableHead>
                <TableHead>Asset</TableHead>
                <TableHead>Direction</TableHead>
                <TableHead>Confidence</TableHead>
                <TableHead>Grade</TableHead>
                <TableHead>Expiry</TableHead>
                <TableHead>Entry</TableHead>
                <TableHead>Close</TableHead>
                <TableHead>Result</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatDateTimeUTC(s.generatedAt)}</TableCell>
                  <TableCell>{ASSET_CONFIGS[s.asset].displayName}</TableCell>
                  <TableCell><DirectionBadge direction={s.direction} /></TableCell>
                  <TableCell className="font-mono-tabular">{s.confidence !== null ? formatPercent(s.confidence) : "—"}</TableCell>
                  <TableCell><GradeBadge grade={s.grade} /></TableCell>
                  <TableCell>{s.expiryMinutes}m</TableCell>
                  <TableCell className="font-mono-tabular">{s.entryPrice ? formatPrice(s.entryPrice, ASSET_CONFIGS[s.asset].pipDecimal) : "—"}</TableCell>
                  <TableCell className="font-mono-tabular">{s.closingPrice ? formatPrice(s.closingPrice, ASSET_CONFIGS[s.asset].pipDecimal) : "—"}</TableCell>
                  <TableCell className={s.result === "WON" ? "font-medium text-call" : s.result === "LOST" ? "font-medium text-put" : "text-muted-foreground"}>{s.result}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

function FilterSelect({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: string[] }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-36"><SelectValue placeholder={label} /></SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o} value={o}>{o === ALL ? `All ${label.toLowerCase()}` : o}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
