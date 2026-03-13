import { render, screen, fireEvent } from "@testing-library/react";
import CallConfirmModal from "../components/CallConfirmModal";

describe("CallConfirmModal", () => {
  it("updates fields and confirms", () => {
    const onChange = vi.fn();
    const onConfirm = vi.fn();
    render(
      <CallConfirmModal
        open
        draft={{ symbol: "AAL", strike: 10, premium: 0.4, dte: 30, expiration: "2026-04-10" }}
        onClose={() => {}}
        onChange={onChange}
        onConfirm={onConfirm}
      />,
    );
    fireEvent.change(screen.getByLabelText(/Strike/i), { target: { value: "11" } });
    expect(onChange).toHaveBeenCalled();
    fireEvent.click(screen.getByText(/Enregistrer/i));
    expect(onConfirm).toHaveBeenCalled();
  });
});
