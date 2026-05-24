"use client";

import { Plus, X } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  buildContract,
  ENTITY_TYPES,
  type EntityType,
  type EvidenceContract,
  type ExpectedClaim,
  type ExpectedEntity,
  JURISDICTIONS,
  type Jurisdiction,
  validateContract,
} from "@/lib/contracts";

// I-p2-041 (#829) P2 visual redo: Contracts was Codex-graded D+ ("raw internal
// form" — native checkboxes/inputs, cramped fieldsets, black default button).
// This rebuilds the VISUAL layer on the design system (Card sections, labelled
// fields, accessible chip-toggles, button hierarchy, tier helper copy) while
// preserving ALL state/logic and every data-testid the e2e suite relies on.

// Kill the bare "T1/T2/T3" jargon: each tier gets a plain-language hint.
const TIER_META = [
  { label: "Tier 1", hint: "RCTs / systematic reviews", testid: "ce-t1" },
  { label: "Tier 2", hint: "guidelines / cohort studies", testid: "ce-t2" },
  { label: "Tier 3", hint: "narrative reviews / context", testid: "ce-t3" },
] as const;

const SELECT_CLASS =
  "border-input focus-visible:border-ring focus-visible:ring-ring/70 ease-standard h-9 rounded-lg border bg-transparent px-2.5 text-sm transition-colors duration-150 outline-none focus-visible:ring-3";

function FieldLabel({
  children,
  hint,
}: {
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <span className="flex flex-col gap-0.5">
      <span className="text-foreground text-sm font-medium">{children}</span>
      {hint ? (
        <span className="text-muted-foreground text-xs">{hint}</span>
      ) : null}
    </span>
  );
}

export function ContractEditor() {
  const [research_question, set_q] = useState("");
  const [created_by, set_by] = useState("");
  const [jurisdictions, set_jurs] = useState<Jurisdiction[]>(["CA"]);
  const [t1, set_t1] = useState(0);
  const [t2, set_t2] = useState(0);
  const [t3, set_t3] = useState(0);
  const [entities, set_entities] = useState<ExpectedEntity[]>([
    { name: "", aliases: [], entity_type: "drug" },
  ]);
  const [claims, set_claims] = useState<ExpectedClaim[]>([
    {
      claim_id: "c1",
      statement: "",
      expected_entities: [],
      required_jurisdictions: ["CA"],
    },
  ]);
  const [errs, set_errs] = useState<string[]>([]);
  const [saved, set_saved] = useState<EvidenceContract | null>(null);
  const tier_setters = [set_t1, set_t2, set_t3] as const;
  const tier_values = [t1, t2, t3] as const;
  const pruned_claims = useMemo(
    () =>
      claims.map((cl) => ({
        ...cl,
        required_jurisdictions: cl.required_jurisdictions.filter((j) =>
          jurisdictions.includes(j),
        ),
      })),
    [claims, jurisdictions],
  );

  function on_submit() {
    const c = buildContract({
      research_question,
      created_by,
      jurisdictions,
      expected_entities: entities,
      expected_claims: pruned_claims,
      expected_source_coverage: {
        tier_t1_min: t1,
        tier_t2_min: t2,
        tier_t3_min: t3,
      },
    });
    const e = validateContract(c);
    set_errs(e);
    if (e.length === 0) {
      set_saved(c);
      const blob = new Blob([JSON.stringify(c, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `contract_${c.contract_id.slice(0, 8)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    }
  }

  function toggle_jur(j: Jurisdiction, on: boolean) {
    set_jurs(on ? [...jurisdictions, j] : jurisdictions.filter((x) => x !== j));
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        on_submit();
      }}
      data-testid="contract-form"
      className="flex flex-col gap-5"
    >
      {/* The question */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">The question</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <label className="flex flex-col gap-1.5">
            <FieldLabel>Research question</FieldLabel>
            <Input
              data-testid="ce-question"
              value={research_question}
              onChange={(e) => set_q(e.target.value)}
              placeholder="e.g. What is the efficacy and safety of tirzepatide in type 2 diabetes?"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <FieldLabel hint="Recorded on the contract for the audit trail.">
              Created by
            </FieldLabel>
            <Input
              data-testid="ce-by"
              value={created_by}
              onChange={(e) => set_by(e.target.value)}
              placeholder="Your name or team"
              className="max-w-xs"
            />
          </label>
        </CardContent>
      </Card>

      {/* Scope: jurisdictions + coverage */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Scope &amp; coverage</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <div className="flex flex-col gap-2">
            <FieldLabel hint="Which regulatory jurisdictions the brief must address.">
              Jurisdictions
            </FieldLabel>
            <div className="flex flex-wrap gap-2">
              {JURISDICTIONS.map((j) => {
                const active = jurisdictions.includes(j);
                return (
                  <label
                    key={j}
                    className={`focus-within:ring-ring/70 ease-standard cursor-pointer rounded-full border px-3 py-1 text-xs font-medium transition-colors duration-150 focus-within:ring-2 ${
                      active
                        ? "border-primary bg-primary/10 text-foreground"
                        : "border-border text-muted-foreground hover:bg-muted"
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="sr-only"
                      data-testid={`ce-jur-${j}`}
                      checked={active}
                      onChange={(e) => toggle_jur(j, e.target.checked)}
                    />
                    {j}
                  </label>
                );
              })}
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <FieldLabel hint="Minimum sources of each evidence tier the report must cite before generation is allowed.">
              Minimum source coverage
            </FieldLabel>
            <div className="grid max-w-md grid-cols-3 gap-3">
              {TIER_META.map((tier, i) => (
                <label key={tier.testid} className="flex flex-col gap-1">
                  <span className="text-foreground text-sm font-medium">
                    {tier.label}
                  </span>
                  <Input
                    data-testid={tier.testid}
                    type="number"
                    min={0}
                    value={tier_values[i]}
                    onChange={(e) =>
                      tier_setters[i](parseInt(e.target.value) || 0)
                    }
                  />
                  <span className="text-muted-foreground text-[11px] leading-tight">
                    {tier.hint}
                  </span>
                </label>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Entities */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Expected entities</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {entities.map((ent, i) => (
            <div
              key={i}
              className="flex flex-col gap-2 sm:flex-row sm:items-center"
            >
              <Input
                data-testid={`ce-ent-name-${i}`}
                placeholder="Entity name (e.g. tirzepatide)"
                value={ent.name}
                onChange={(e) => {
                  const n = [...entities];
                  n[i] = { ...ent, name: e.target.value };
                  set_entities(n);
                }}
                className="flex-1"
              />
              <select
                data-testid={`ce-ent-type-${i}`}
                aria-label={`Entity type for ${ent.name || `entity ${i + 1}`}`}
                value={ent.entity_type}
                onChange={(e) => {
                  const n = [...entities];
                  n[i] = { ...ent, entity_type: e.target.value as EntityType };
                  set_entities(n);
                }}
                className={SELECT_CLASS}
              >
                {ENTITY_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              {entities.length > 1 && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  data-testid={`ce-rm-ent-${i}`}
                  aria-label="Remove entity"
                  onClick={() =>
                    set_entities(entities.filter((_, j) => j !== i))
                  }
                >
                  <X aria-hidden className="h-4 w-4" />
                </Button>
              )}
            </div>
          ))}
          <Button
            type="button"
            variant="outline"
            size="sm"
            data-testid="ce-add-entity"
            className="w-fit"
            onClick={() =>
              set_entities([
                ...entities,
                { name: "", aliases: [], entity_type: "drug" },
              ])
            }
          >
            <Plus aria-hidden className="h-4 w-4" /> Add entity
          </Button>
        </CardContent>
      </Card>

      {/* Claims */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Expected claims</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {pruned_claims.map((cl, i) => (
            <div
              key={i}
              className="border-border flex flex-col gap-2 rounded-lg border p-3"
            >
              <div className="flex items-center justify-between gap-2">
                <Input
                  data-testid={`ce-claim-id-${i}`}
                  placeholder="claim id"
                  value={cl.claim_id}
                  onChange={(e) => {
                    const n = [...claims];
                    n[i] = { ...cl, claim_id: e.target.value };
                    set_claims(n);
                  }}
                  className="w-24 font-mono"
                />
                {claims.length > 1 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    data-testid={`ce-rm-claim-${i}`}
                    onClick={() => set_claims(claims.filter((_, j) => j !== i))}
                  >
                    <X aria-hidden className="h-4 w-4" /> Remove
                  </Button>
                )}
              </div>
              <Input
                data-testid={`ce-claim-stmt-${i}`}
                placeholder="Claim the brief must support"
                value={cl.statement}
                onChange={(e) => {
                  const n = [...claims];
                  n[i] = { ...cl, statement: e.target.value };
                  set_claims(n);
                }}
              />
              <Input
                data-testid={`ce-claim-ents-${i}`}
                placeholder="Related entities (comma-separated)"
                value={cl.expected_entities.join(",")}
                onChange={(e) => {
                  const n = [...claims];
                  n[i] = {
                    ...cl,
                    expected_entities: e.target.value
                      .split(",")
                      .map((x) => x.trim())
                      .filter(Boolean),
                  };
                  set_claims(n);
                }}
              />
              <div
                data-testid={`ce-claim-jurs-${i}`}
                className="flex flex-wrap items-center gap-2"
              >
                <span className="text-muted-foreground text-xs">
                  Required in:
                </span>
                {jurisdictions.map((j) => {
                  const on = cl.required_jurisdictions.includes(j);
                  return (
                    <label
                      key={j}
                      className={`focus-within:ring-ring/70 cursor-pointer rounded-full border px-2.5 py-0.5 text-xs transition-colors focus-within:ring-2 ${
                        on
                          ? "border-primary bg-primary/10 text-foreground"
                          : "border-border text-muted-foreground hover:bg-muted"
                      }`}
                    >
                      <input
                        type="checkbox"
                        className="sr-only"
                        data-testid={`ce-claim-${i}-jur-${j}`}
                        checked={on}
                        onChange={(e) => {
                          const n = [...claims];
                          n[i] = {
                            ...cl,
                            required_jurisdictions: e.target.checked
                              ? [...cl.required_jurisdictions, j]
                              : cl.required_jurisdictions.filter(
                                  (x) => x !== j,
                                ),
                          };
                          set_claims(n);
                        }}
                      />
                      {j}
                    </label>
                  );
                })}
              </div>
            </div>
          ))}
          <Button
            type="button"
            variant="outline"
            size="sm"
            data-testid="ce-add-claim"
            className="w-fit"
            onClick={() =>
              set_claims([
                ...claims,
                {
                  claim_id: `c${claims.length + 1}`,
                  statement: "",
                  expected_entities: [],
                  required_jurisdictions: [...jurisdictions],
                },
              ])
            }
          >
            <Plus aria-hidden className="h-4 w-4" /> Add claim
          </Button>
        </CardContent>
      </Card>

      {errs.length > 0 && (
        <div
          role="alert"
          data-testid="contract-errors"
          className="border-destructive/30 bg-destructive/10 text-foreground flex flex-col gap-1 rounded-lg border p-3 text-sm"
        >
          <span className="font-medium">Fix before saving:</span>
          <ul className="text-muted-foreground list-disc pl-5">
            {errs.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      )}

      {/* I-p2-046 (#839): crafted action bar (ring + brand shadow + explainer) — a
          static dock at the form end, NOT sticky, so it never overlays editable
          fields (Codex visual iter-1 P1). Inside <form> so contract-submit submits;
          contract-saved + contract-errors testids unchanged. */}
      <div className="bg-card ring-foreground/10 shadow-card mt-1 flex flex-wrap items-center gap-3 rounded-xl px-4 py-3 ring-1">
        <Button
          type="submit"
          data-testid="contract-submit"
          className="h-10 px-6"
        >
          Save + download
        </Button>
        {saved ? (
          <p
            data-testid="contract-saved"
            className="text-verified text-sm font-medium"
          >
            Contract {saved.contract_id.slice(0, 8)} saved.
          </p>
        ) : (
          <span className="text-muted-foreground text-xs">
            Downloads the signed contract JSON. The Evidence Contract Gate
            enforces it before generation runs.
          </span>
        )}
      </div>
    </form>
  );
}
