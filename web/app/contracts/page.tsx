import { ContractEditor } from "./_editor";

export const metadata = {
  title: "Evidence Contract editor — POLARIS Canada",
  description:
    "Declare expected entities, claims, jurisdictions, and source coverage before generation runs.",
};

// I-cd-028 (#618): /contracts rebuild — G1+G6 fix. Page uses
// AppShell's <main> via the wrapper <section data-testid="contracts-page">.
// G2: removed Issue id + env-var name from user-visible copy.
export default function ContractsPage() {
  return (
    <section
      data-testid="contracts-page"
      className="mx-auto max-w-3xl px-6 py-8"
    >
      <h1 className="mb-2 text-2xl font-semibold">Evidence Contract editor</h1>
      <p className="text-muted-foreground mb-6 text-sm">
        Define what the report must address before generation runs. The Evidence
        Contract Gate refuses generation when the contract is missing or
        unsatisfied (configurable per deployment).
      </p>
      <ContractEditor />
    </section>
  );
}
