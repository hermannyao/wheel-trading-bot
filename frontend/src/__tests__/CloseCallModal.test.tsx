import { render, screen, fireEvent } from "@testing-library/react";
import CloseCallModal from "../components/CloseCallModal";

const formatMoney = (value: number) => `${value}$`;
const formatPct = (value: number) => `${value}%`;

describe("CloseCallModal", () => {
  it("renders impact and triggers confirm", () => {
    const onConfirm = vi.fn();
    render(
      <CloseCallModal
        open
        symbol="AAL"
        strike={10.5}
        scenario="exerced"
        buyback=""
        impact={{
          current_cost_basis: 9.3,
          new_cost_basis: 9.3,
          total_premiums: 0.7,
          total_premiums_after: 0.7,
          pnl_total: 120,
          pnl_pct: 12,
          delivery_price: 10.5,
          capital_initial: 1000,
        }}
        impactError=""
        onScenarioChange={() => {}}
        onBuybackChange={() => {}}
        onClose={() => {}}
        onConfirm={onConfirm}
        formatMoney={formatMoney}
        formatPct={formatPct}
      />,
    );
    expect(screen.getByText(/Call exercé/i)).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Confirmer/i));
    expect(onConfirm).toHaveBeenCalled();
  });
});
