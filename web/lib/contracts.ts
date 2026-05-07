// I-ecg-003 — frontend mirror of src/polaris_graph/evidence_contract/schema.py
// (NOT web/lib/api.ts post-run EvidenceContract).

export type Jurisdiction = "CA" | "US" | "EU" | "UK" | "GLOBAL";
export const JURISDICTIONS: Jurisdiction[] = ["CA", "US", "EU", "UK", "GLOBAL"];
export type EntityType =
  | "drug"
  | "condition"
  | "intervention"
  | "population"
  | "outcome";
export const ENTITY_TYPES: EntityType[] = [
  "drug",
  "condition",
  "intervention",
  "population",
  "outcome",
];

export interface ExpectedEntity {
  name: string;
  aliases: string[];
  entity_type: EntityType;
}
export interface ExpectedClaim {
  claim_id: string;
  statement: string;
  expected_entities: string[];
  required_jurisdictions: Jurisdiction[];
}
export interface ExpectedSourceCoverage {
  tier_t1_min: number;
  tier_t2_min: number;
  tier_t3_min: number;
}
export interface EvidenceContract {
  contract_id: string;
  contract_version: "1.0";
  research_question: string;
  expected_entities: ExpectedEntity[];
  expected_claims: ExpectedClaim[];
  expected_source_coverage: ExpectedSourceCoverage;
  jurisdictions: Jurisdiction[];
  created_at_utc: string;
  created_by: string;
}

function uuid(): string {
  return (
    globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)
  );
}

export function buildContract(
  args: Omit<
    EvidenceContract,
    "contract_id" | "contract_version" | "created_at_utc"
  >,
): EvidenceContract {
  return {
    contract_id: uuid(),
    contract_version: "1.0",
    created_at_utc: new Date().toISOString(),
    ...args,
  };
}

export function validateContract(c: EvidenceContract): string[] {
  const errs: string[] = [];
  if (!c.research_question.trim()) errs.push("research_question required");
  if (!c.created_by.trim()) errs.push("created_by required");
  if (c.expected_entities.length === 0) errs.push("at least 1 entity required");
  if (c.expected_claims.length === 0) errs.push("at least 1 claim required");
  if (c.jurisdictions.length === 0)
    errs.push("at least 1 jurisdiction required");
  for (const e of c.expected_entities) {
    if (!e.name.trim()) errs.push("entity name required");
  }
  const cov = c.expected_source_coverage;
  for (const [k, v] of Object.entries(cov)) {
    if (v < 0 || v > 100) errs.push(`${k} must be in [0, 100]`);
  }
  const names = c.expected_entities.map((e) => e.name);
  if (new Set(names).size !== names.length)
    errs.push("duplicate entity name(s)");
  const ids = c.expected_claims.map((cl) => cl.claim_id);
  if (new Set(ids).size !== ids.length) errs.push("duplicate claim_id(s)");
  const declared = new Set(names);
  const cjurs = new Set(c.jurisdictions);
  for (const cl of c.expected_claims) {
    if (!cl.claim_id.trim()) errs.push("claim_id required");
    if (!cl.statement.trim())
      errs.push(`claim ${cl.claim_id} statement required`);
    if (cl.expected_entities.length === 0)
      errs.push(`claim ${cl.claim_id} expected_entities required`);
    if (cl.required_jurisdictions.length === 0)
      errs.push(`claim ${cl.claim_id} required_jurisdictions required`);
    for (const e of cl.expected_entities) {
      if (!declared.has(e))
        errs.push(`claim ${cl.claim_id} references undeclared entity ${e}`);
    }
    for (const j of cl.required_jurisdictions) {
      if (!cjurs.has(j))
        errs.push(
          `claim ${cl.claim_id} jurisdiction ${j} not in contract jurisdictions`,
        );
    }
  }
  return errs;
}
