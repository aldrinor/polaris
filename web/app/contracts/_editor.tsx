"use client";

import { useMemo, useState } from "react";

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

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        on_submit();
      }}
      data-testid="contract-form"
      className="space-y-4 text-sm"
    >
      <label className="block">
        <span>Research question</span>
        <input
          data-testid="ce-question"
          value={research_question}
          onChange={(e) => set_q(e.target.value)}
          className="border-input mt-1 w-full rounded border p-2"
        />
      </label>
      <label className="block">
        <span>Created by</span>
        <input
          data-testid="ce-by"
          value={created_by}
          onChange={(e) => set_by(e.target.value)}
          className="border-input mt-1 w-full rounded border p-2"
        />
      </label>
      <fieldset className="border-border rounded border p-3">
        <legend>Jurisdictions</legend>
        {JURISDICTIONS.map((j) => (
          <label key={j} className="mr-3 inline-flex items-center gap-1">
            <input
              type="checkbox"
              data-testid={`ce-jur-${j}`}
              checked={jurisdictions.includes(j)}
              onChange={(e) =>
                set_jurs(
                  e.target.checked
                    ? [...jurisdictions, j]
                    : jurisdictions.filter((x) => x !== j),
                )
              }
            />
            {j}
          </label>
        ))}
      </fieldset>
      <fieldset className="border-border rounded border p-3">
        <legend>Source coverage (min)</legend>
        <label className="mr-3">
          T1{" "}
          <input
            data-testid="ce-t1"
            type="number"
            min={0}
            value={t1}
            onChange={(e) => set_t1(parseInt(e.target.value) || 0)}
            className="border-input w-16 rounded border p-1"
          />
        </label>
        <label className="mr-3">
          T2{" "}
          <input
            data-testid="ce-t2"
            type="number"
            min={0}
            value={t2}
            onChange={(e) => set_t2(parseInt(e.target.value) || 0)}
            className="border-input w-16 rounded border p-1"
          />
        </label>
        <label className="mr-3">
          T3{" "}
          <input
            data-testid="ce-t3"
            type="number"
            min={0}
            value={t3}
            onChange={(e) => set_t3(parseInt(e.target.value) || 0)}
            className="border-input w-16 rounded border p-1"
          />
        </label>
      </fieldset>
      <fieldset className="border-border rounded border p-3">
        <legend>Entities</legend>
        {entities.map((ent, i) => (
          <div key={i} className="mb-2 flex gap-2">
            <input
              data-testid={`ce-ent-name-${i}`}
              placeholder="name"
              value={ent.name}
              onChange={(e) => {
                const n = [...entities];
                n[i] = { ...ent, name: e.target.value };
                set_entities(n);
              }}
              className="border-input flex-1 rounded border p-1"
            />
            <select
              data-testid={`ce-ent-type-${i}`}
              value={ent.entity_type}
              onChange={(e) => {
                const n = [...entities];
                n[i] = { ...ent, entity_type: e.target.value as EntityType };
                set_entities(n);
              }}
              className="border-input rounded border p-1"
            >
              {ENTITY_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            {entities.length > 1 && (
              <button
                type="button"
                data-testid={`ce-rm-ent-${i}`}
                onClick={() => set_entities(entities.filter((_, j) => j !== i))}
                className="text-xs underline"
              >
                ×
              </button>
            )}
          </div>
        ))}
        <button
          type="button"
          data-testid="ce-add-entity"
          onClick={() =>
            set_entities([
              ...entities,
              { name: "", aliases: [], entity_type: "drug" },
            ])
          }
          className="text-xs underline"
        >
          + entity
        </button>
      </fieldset>
      <fieldset className="border-border rounded border p-3">
        <legend>Claims</legend>
        {pruned_claims.map((cl, i) => (
          <div key={i} className="mb-2 flex flex-col gap-1">
            <input
              data-testid={`ce-claim-id-${i}`}
              placeholder="claim_id"
              value={cl.claim_id}
              onChange={(e) => {
                const n = [...claims];
                n[i] = { ...cl, claim_id: e.target.value };
                set_claims(n);
              }}
              className="border-input rounded border p-1"
            />
            <input
              data-testid={`ce-claim-stmt-${i}`}
              placeholder="statement"
              value={cl.statement}
              onChange={(e) => {
                const n = [...claims];
                n[i] = { ...cl, statement: e.target.value };
                set_claims(n);
              }}
              className="border-input rounded border p-1"
            />
            <input
              data-testid={`ce-claim-ents-${i}`}
              placeholder="entities (comma-sep)"
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
              className="border-input rounded border p-1"
            />
            <div
              data-testid={`ce-claim-jurs-${i}`}
              className="flex flex-wrap gap-2 text-xs"
            >
              {jurisdictions.map((j) => (
                <label key={j} className="inline-flex items-center gap-1">
                  <input
                    type="checkbox"
                    data-testid={`ce-claim-${i}-jur-${j}`}
                    checked={cl.required_jurisdictions.includes(j)}
                    onChange={(e) => {
                      const n = [...claims];
                      n[i] = {
                        ...cl,
                        required_jurisdictions: e.target.checked
                          ? [...cl.required_jurisdictions, j]
                          : cl.required_jurisdictions.filter((x) => x !== j),
                      };
                      set_claims(n);
                    }}
                  />
                  {j}
                </label>
              ))}
            </div>
            {claims.length > 1 && (
              <button
                type="button"
                data-testid={`ce-rm-claim-${i}`}
                onClick={() => set_claims(claims.filter((_, j) => j !== i))}
                className="self-start text-xs underline"
              >
                × remove
              </button>
            )}
          </div>
        ))}
        <button
          type="button"
          data-testid="ce-add-claim"
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
          className="text-xs underline"
        >
          + claim
        </button>
      </fieldset>
      {errs.length > 0 && (
        <ul
          data-testid="contract-errors"
          className="text-rose-700 dark:text-rose-300"
        >
          {errs.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      )}
      <button
        type="submit"
        data-testid="contract-submit"
        className="bg-foreground text-background rounded px-4 py-2"
      >
        Save + download
      </button>
      {saved && (
        <p
          data-testid="contract-saved"
          className="text-green-700 dark:text-green-300"
        >
          Contract {saved.contract_id.slice(0, 8)} saved.
        </p>
      )}
    </form>
  );
}
