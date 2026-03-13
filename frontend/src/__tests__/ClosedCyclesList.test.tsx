import { render, screen, fireEvent } from "@testing-library/react";
import ClosedCyclesList from "../components/ClosedCyclesList";
import type { ClosedCycle } from "../types";

const formatMoney = (value: number) => `${value}$`;
const formatPct = (value: number) => `${value}%`;

describe("ClosedCyclesList", () => {
  it("renders empty state", () => {
    render(
      <ClosedCyclesList
        cycles={[]}
        onNewCycle={() => {}}
        formatMoney={formatMoney}
        formatPct={formatPct}
      />,
    );
    expect(screen.getByText(/Aucun cycle clôturé/i)).toBeInTheDocument();
  });

  it("renders cycles and triggers new cycle", () => {
    const cycles: ClosedCycle[] = [
      {
        position_id: 1,
        symbol: "AAL",
        closed_at: "2026-03-12T00:00:00Z",
        capital_initial: 1800,
        total_premiums: 0.5,
        delivery_price: 19,
        pnl_total: 250,
        pnl_pct: 12.3,
        duration_days: 40,
        contracts: 1,
        legs: [],
      },
    ];
    const onNewCycle = vi.fn();
    render(
      <ClosedCyclesList
        cycles={cycles}
        onNewCycle={onNewCycle}
        formatMoney={formatMoney}
        formatPct={formatPct}
      />,
    );
    expect(screen.getByText("AAL")).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Nouveau cycle/i));
    expect(onNewCycle).toHaveBeenCalledWith(1800);
  });
});
