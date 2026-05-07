import { ContractEditor } from "./_editor";

export const metadata = {
  title: "Evidence Contract editor — POLARIS Canada",
  description:
    "Declare expected entities, claims, jurisdictions, and source coverage before generation runs.",
};

export default function ContractsPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <h1 className="mb-2 text-2xl font-semibold">Evidence Contract editor</h1>
      <p className="text-muted-foreground mb-6 text-sm">
        Define what the report MUST address before generation runs. The Evidence
        Contract Gate (I-ecg-002) will refuse generation if the contract is
        missing or unsatisfied (when POLARIS_REQUIRE_CONTRACT=1).
      </p>
      <ContractEditor />
    </div>
  );
}
