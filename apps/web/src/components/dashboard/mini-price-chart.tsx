"use client";
import { LineChart, Line, ResponsiveContainer, YAxis, ReferenceLine, Tooltip } from "recharts";
import { seededRandom, range } from "@/data/rng";
import type { Direction } from "@/types";

export function MiniPriceChart({ id, entryPrice, direction }: { id: string; entryPrice: number; direction: Direction }) {
  const rand = seededRandom(id, "chart");
  const points: { i: number; price: number }[] = [];
  let price = entryPrice * (1 - range(rand, 0.001, 0.004));
  for (let i = 0; i < 40; i++) {
    const drift = direction === "CALL" ? 0.00015 : direction === "PUT" ? -0.00015 : 0;
    price = price * (1 + drift + range(rand, -0.0009, 0.0009));
    points.push({ i, price });
  }
  // Pin the last point near the entry price for visual continuity.
  points.push({ i: 40, price: entryPrice });

  return (
    <div className="h-40 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
          <YAxis domain={["auto", "auto"]} hide />
          <ReferenceLine y={entryPrice} stroke="hsl(var(--primary))" strokeDasharray="4 4" strokeOpacity={0.6} />
          <Tooltip
            contentStyle={{ background: "hsl(var(--popover))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }}
            labelFormatter={() => ""}
            formatter={(value: number) => [value.toFixed(4), "Price"]}
          />
          <Line type="monotone" dataKey="price" stroke="hsl(var(--foreground))" strokeWidth={1.75} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
