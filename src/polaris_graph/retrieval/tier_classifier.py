"""
Tier classifier for retrieved sources — T1 through T7 + UNKNOWN.

Part of HONEST-REBUILD Phase 2 (plan:
C:/Users/msn/.claude/plans/lovely-finding-firefly.md).

Classifies every retrieved URL at fetch time into a tier so the pipeline
can surface the corpus quality distribution to the user BEFORE composition
starts. Fixes the defects documented in PG_LB_SA_02_CONTENT_AUDIT.md
Section E-01:
    - Patch D over-assigned GOLD at ~24% error rate
    - Novo HCP portals tagged GOLD (should be BRONZE/industry)
    - News and student journals tagged GOLD
    - Regulatory documents (CDA-AMC) tagged UNKNOWN when they should be GOLD
    - No-match defaulted to BRONZE silently

Key discipline:
    1. UNKNOWN on no-match (NOT silent BRONZE) — surfaces misconfiguration
       rather than hiding it. The plan A-F04 "UNKNOWN ambiguity" gets
       resolved by BRONZE vs UNKNOWN being meaningfully different:
       UNKNOWN = "rules could not decide; requires user review";
       BRONZE = "rules positively identified low-tier source".
    2. Rules fire in priority order; first match wins.
    3. Each ClassificationResult carries the reasons list so the user
       can audit the decision (and so later reshapes can pin regressions
       to specific rule matches).
    4. No LLM call in the classifier — pure rules. An LLM-in-the-loop
       variant may come later, but for Phase 2 a deterministic classifier
       is the right primitive.

Tier taxonomy:
    T1 — Peer-reviewed primary study (RCT, prospective cohort, case-control,
          cross-sectional with clear protocol, ClinicalTrials.gov with
          results, etc.)
    T2 — Peer-reviewed systematic review, meta-analysis, Cochrane review,
          network meta-analysis
    T3 — Government / regulatory body (FDA, EMA, NICE, CDA-AMC, WHO,
          MHRA, Health Canada, TGA, PMDA)
    T4 — Peer-reviewed narrative review, commentary, editorial, perspective
    T5 — Industry-funded report (pharmaceutical company HCP portal, drug
          monograph from manufacturer, industry advocacy with funding
          disclosure)
    T6 — News / blog / non-peer-reviewed web content (mainstream news,
          industry press release distribution, commentary blog)
    T7 — Abstract-only / conference abstract / Semantic Scholar stub
          (content < 1000 chars) / paper behind paywall where only title
          + abstract were retrieved
    UNKNOWN — rules could not decide; user review required

Non-goals of this module:
    - Not a quality judgment of the CONTENT (that's the evaluator's job)
    - Not a hallucination detector (that's Vectara / our Phase 5 evaluator)
    - Not a plagiarism / novelty checker
    - Not a decision about whether to INCLUDE the source — only how to
      label it. The user (or auto-mode rules) decides inclusion.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class TierLevel(str, Enum):
    """Seven tiers plus UNKNOWN for surfacing classifier misconfiguration."""

    T1 = "T1"  # Peer-reviewed primary study
    T2 = "T2"  # Peer-reviewed SR / MA
    T3 = "T3"  # Government / regulatory
    T4 = "T4"  # Peer-reviewed narrative / commentary
    T5 = "T5"  # Industry-funded
    T6 = "T6"  # News / blog / non-peer-reviewed
    T7 = "T7"  # Abstract-only / stub
    UNKNOWN = "UNKNOWN"  # Rules could not decide — user review needed


@dataclass
class ClassificationSignals:
    """Input signals the classifier uses. All optional — partial signals OK."""

    url: str = ""
    fetched_content_length: int = 0  # chars of body fetched
    # OpenAlex-derived fields (when available)
    openalex_publication_type: str = ""  # "article", "preprint", "review", ...
    openalex_source_type: str = ""       # "journal", "repository", ...
    openalex_is_retracted: bool = False
    openalex_venue: str = ""             # journal or venue name
    openalex_is_peer_reviewed: bool | None = None  # None = unknown
    # I-ready-017 #1134: article DOI (normalized, no scheme). ADDITIVE — the
    # legacy rule body NEVER reads it; consumed only by the journal_only filter
    # (src/polaris_graph/nodes/journal_only_filter.py) on the ON path. Default
    # "" = byte-identical to HEAD.
    doi: str = ""
    # Bibliography-layer fields (when available)
    source_type_hint: str = ""  # upstream string like "industry_report"
    publisher: str = ""
    author_affiliations: list[str] = field(default_factory=list)
    funding_disclosures: list[str] = field(default_factory=list)
    # Free text for future keyword rules (e.g., title keywords)
    title: str = ""
    # BUG-M-17 (Codex pass 2): body-inspection secondary signal.
    # One of "SR_MA", "CASE_REPORT", "PERSPECTIVE", "GUIDELINE", or "".
    # Populated by live_retriever._detect_article_type_from_body when
    # fetched content contains article-type metadata or SR/MA/case-
    # report markers in the first 8KB. Used by classifier to override
    # title-only decisions when body evidence contradicts.
    body_article_type: str = ""
    # ── Phase 0a (GH #983) ADDITIVE fields — consumed ONLY by the authority
    # model when PG_USE_AUTHORITY_MODEL=ON. The legacy rule body
    # (_classify_source_tier_rules) NEVER reads these, so OFF behaviour is
    # byte-identical to HEAD. `authority` is the C1 AuthoritySignals payload
    # (default None -> model degrades to LOW confidence, never fabricates).
    authority: "AuthoritySignals | None" = None
    fetched_body: str = ""          # optional structural body for junk detection
    structured_jsonld: str = ""     # optional extracted JSON-LD for junk/self-desc
    claim_vendor_token: str = ""    # optional claim-vendor token for self-interest


@dataclass
class ClassificationResult:
    """What the classifier returns. Always includes the reasoning trail."""

    tier: TierLevel
    confidence: float  # 0.0-1.0; 1.0 for deterministic rules, <1 for fuzzy
    reasons: list[str] = field(default_factory=list)
    matched_rules: list[str] = field(default_factory=list)
    signals_used: dict[str, Any] = field(default_factory=dict)
    # ── Phase 0a (GH #983) ADDITIVE fields. Default None on the OFF path
    # (byte-identical to HEAD for existing consumers). Populated ONLY by
    # _classify_via_authority_model when PG_USE_AUTHORITY_MODEL=ON; emitted
    # but inert (no downstream gate reads them) in 0a — shadow only.
    authority_score: float | None = None
    source_class: str | None = None
    corroboration_count: int | None = None
    authority_confidence: str | None = None

    @property
    def is_decided(self) -> bool:
        return self.tier != TierLevel.UNKNOWN


# ─────────────────────────────────────────────────────────────────────────────
# Domain sets.
# ─────────────────────────────────────────────────────────────────────────────

# Regulatory bodies (T3). Extendable via config later.
#
# CRITICAL: Do NOT include ncbi.nlm.nih.gov, pmc.ncbi.nlm.nih.gov,
# pubmed.ncbi.nlm.nih.gov here. Those are NIH-hosted peer-reviewed
# journal aggregators — T1/T2/T4 based on content, NOT T3 regulatory.
# The subdomain overlap with nih.gov is misleading.
REGULATORY_DOMAINS = frozenset({
    # US
    "fda.gov", "accessdata.fda.gov", "nctr-crs.fda.gov",
    "cdc.gov", "nasa.gov",
    "clinicaltrials.gov",
    # EU
    "ema.europa.eu", "europa.eu",
    # UK
    "nice.org.uk", "mhra.gov.uk", "gov.uk",
    # Canada
    "cda-amc.ca", "hc-sc.gc.ca", "canada.ca",
    "hres.ca",   # M-37: Health Canada DPD Product Monograph PDFs
                 # (pdf.hres.ca via parent-domain match). Without this
                 # the MOUNJARO monograph fell through to R9 OpenAlex
                 # and got demoted T4 instead of T3 regulatory.
    # Australia / NZ
    "tga.gov.au", "medsafe.govt.nz",
    # Japan
    "pmda.go.jp",
    # International
    "who.int", "iarc.who.int",
    # Other national
    "bfarm.de", "ansm.sante.fr",
})

# Explicit NIH literature-aggregator hosts. These are peer-reviewed
# journal content; route through the peer-review journal rule, not
# through regulatory.
NIH_LITERATURE_HOSTS = frozenset({
    "ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov",
    "pmc.ncbi.nlm.nih.gov",
    "pubmed.ncbi.nlm.nih.gov",
    "nlm.nih.gov",
})

# Pharmaceutical-industry HCP portals and brand sites (T5). These are
# manufacturer-controlled pages; peer-reviewed content from the same
# company (e.g., an investigator-authored RCT paper) is T1/T4 via its
# journal URL, not via these domains. MEMORY lesson: Patch D tagged
# these GOLD; they are industry-marketing.
INDUSTRY_MARKETING_DOMAINS = frozenset({
    # Novo Nordisk — corporate, HCP, medical education, research portal.
    # Live-run FP-1 (2026-04-18): OpenAlex tiered novonordiskmedical.com
    # as T1 peer-reviewed. Added medical / sciencehub / nnmedinfo variants.
    "novomedlink.com", "wegovy.com", "ozempic.com", "novonordisk.com",
    "novonordisk.ca", "novomedinfo.com", "nnmedinfo.com",
    "novonordiskmedical.com", "novonordiskpro.com",
    "sciencehub.novonordisk.com",
    # Eli Lilly
    "lilly.com", "mounjaro.com", "zepbound.com",
    "lillymedical.com", "lillypro.com",
    # Pfizer
    "pfizer.com", "pfizermedicalinformation.com", "pfizermedical.com",
    "pfizerpro.com",
    # Merck
    "merck.com", "merckconnect.com", "merckmanuals.com",
    # GSK
    "gsk.com", "gskpro.com", "gskmedical.com",
    # AstraZeneca
    "astrazeneca.com", "azmedical.us", "azmerck.com",
    # Roche / Genentech
    "roche.com", "genentech.com", "gene.com", "rochemedical.com",
    # Sanofi
    "sanofi.com", "sanofimedicalinformation.com", "sanofimedical.com",
    # Bayer
    "bayer.com", "pharma.bayer.com",
    # Boehringer Ingelheim
    "boehringer-ingelheim.com", "bipharma.com",
    # Takeda
    "takeda.com",
    # Johnson & Johnson
    "jnj.com", "janssen.com", "janssenmd.com",
    # Bristol Myers Squibb
    "bms.com", "bmsstudyconnect.com",
    # Abbvie
    "abbvie.com", "abbviepro.com",
})

# Branded physician-portal domains that LOOK like journals but are
# industry-adjacent commentary sites (T5 / T6 depending on sponsorship
# transparency). Added in response to PG_LB_SA_02 spot-check: [16] and
# [30] touchendocrinology.com "game-changer" commentary got T1'd by
# rules; these domains do not do independent peer review.
PHYSICIAN_PORTAL_COMMENTARY_DOMAINS = frozenset({
    "touchendocrinology.com", "touchneurology.com",
    "touchoncology.com", "touchcardio.com", "touchrespiratory.com",
    "touchimmunology.com", "touchgastroenterology.com",
    "medscape.com",  # often commentary + CME, not primary
})

# Low-provenance document hosts (T6). A government document re-hosted
# on Scribd is not a guaranteed-authentic copy; tier down regardless
# of source_type_hint. Patch C / Patch D called these GOLD/government
# via upstream metadata, which was the F-05-adjacent defect.
LOW_PROVENANCE_HOSTS = frozenset({
    "scribd.com", "slideshare.net", "academia.edu",
    "researchgate.net",  # author-uploaded reprints; not a peer-review venue
    "issuu.com", "docdroid.net",
})

# Law-firm and consulting-firm commentary sites (T6). Legal opinions
# and pharma-regulatory analysis; not peer-reviewed research.
LEGAL_COMMENTARY_DOMAINS = frozenset({
    "bipc.com", "buchananingersoll.com",
    "ropesgray.com", "reedsmith.com",
    "cov.com", "sullcrom.com",
    "natlawreview.com", "lexology.com",
    "law360.com", "mcguirewoods.com",
    # R-5 Fix A: healthcare regulatory consulting firms were being
    # tiered T1 via OpenAlex because they publish blog-style analysis
    # of FDA decisions. Not peer-reviewed research.
    "mcdermottplus.com", "mcdermottwill.com",
    "hoganlovells.com", "faegredrinker.com",
    "ropesandgray.com",
    # Pass-9 additions (Codex found these classified as T1 in released
    # reports): IP / pharma law-firm blogs that OpenAlex sometimes
    # flags as 'article' in 'journal' source_type because they publish
    # alerts and client advisories.
    "knobbe.com", "finnegan.com", "foley.com",
    "jonesday.com", "goodwinlaw.com", "gibsondunn.com",
    "kirkland.com", "lathamwatkins.com", "skadden.com",
    "wsgr.com", "bakermckenzie.com", "whitecase.com",
    "fenwick.com", "cooley.com",
})

# Pass-9 addition (BUG-M-7): social media + general-interest portals.
# Per Codex pass 9 findings, facebook.com, aol.com, reddit.com threads
# were being classified as T1 peer-reviewed via OpenAlex because those
# domains sometimes appear as 'journal' source_type in metadata. They
# are user-generated content, not primary research, full stop.
SOCIAL_PLATFORM_DOMAINS = frozenset({
    # User-generated content
    "facebook.com", "instagram.com", "twitter.com", "x.com",
    "reddit.com", "old.reddit.com", "np.reddit.com",
    "tiktok.com", "youtube.com", "pinterest.com",
    "quora.com", "stackexchange.com", "stackoverflow.com",
    "tumblr.com", "telegram.org",
    # General-interest portals (news-aggregated, blog-style)
    "aol.com", "yahoo.com", "msn.com",
    "buzzfeed.com", "huffpost.com", "vox.com",
    "slate.com", "salon.com", "vice.com",
    # Q&A / forum
    "answers.com", "quora.com", "hubpages.com",
})

# Pass-9 addition (BUG-M-7): market-research / consulting reports.
# Per Codex pass 9 findings, DelveInsight, Statista, MatrixBCG,
# PortersFiveForce, PharmaVoice trade blogs were being classified as
# T1 via OpenAlex. These are paid industry analyses or consulting
# collateral — not peer-reviewed primary research. Mostly legitimate
# T5 / T6 content but MUST NOT be T1.
MARKET_RESEARCH_DOMAINS = frozenset({
    # Pharma/biotech market research
    "delveinsight.com", "globaldata.com", "evaluate.com",
    "evaluatepharma.com", "iqvia.com", "cortellis.com",
    "pharmaintelligence.informa.com", "citeline.com",
    # General market research / consulting
    "statista.com", "matrixbcg.com", "mckinsey.com",
    "bcg.com", "bain.com", "deloitte.com",
    "pwc.com", "accenture.com", "ey.com", "kpmg.com",
    "gartner.com", "forrester.com", "idc.com",
    # Strategy frameworks / business-school blogs
    "portersfiveforce.com", "portersfiveforces.com",
    "mindtools.com", "smartsheet.com",
    # Trade / industry publication blogs (paid or subscription)
    "pharmavoice.com", "pharmexec.com", "pharmaceutical-commerce.com",
    "pharmaceutical-technology.com", "pharmaceutical-business-review.com",
    # Finance / investor commentary with "analysis" framing
    "investopedia.com", "nerdwallet.com",
    # Pass-11 additions (Codex pass 11)
    "vizientinc.com",  # healthcare consulting insights
    "healthcareappraisers.com", "avalere.com", "milliman.com",
    "advisory.com",  # Advisory Board Company
})

# Pass-10 addition (BUG-M-10): clinical reference products (UpToDate,
# etc.) that package existing evidence into clinical decision-support
# summaries. Useful practitioner references but NOT primary research.
# OpenAlex sometimes returns these as 'article' in 'journal' source_type.
CLINICAL_REFERENCE_PRODUCTS = frozenset({
    "uptodate.com", "dynamed.com", "clinicalkey.com",
    "firstchoice.kp.org", "bestpractice.bmj.com",
    "medscape.com/reference",  # handled via path check below too
    "emedicine.medscape.com",
    "merckmanuals.com", "ebmedicine.net",
    "mdcalc.com",  # medical calculator, not primary evidence
})

# Pass-10 addition (BUG-M-10): policy / think-tank / advocacy
# organizations. KFF, Commonwealth Fund, Brookings, etc. produce
# policy analyses and explainers — typically T4 narrative / T6
# commentary depending on rigor, but NEVER T1 primary research.
# Some rise in rigor (Rand, NBER working papers) route to T4 here.
POLICY_THINK_TANK_DOMAINS = frozenset({
    # US health policy
    "kff.org", "commonwealthfund.org", "accessiblemeds.org",
    "healthaffairs.org",  # blog side; the journal itself is PEER_REVIEWED
    "chrt.org", "aha.org", "urban.org",
    # General policy / advocacy
    "brookings.edu", "rand.org", "heritage.org",
    "cato.org", "aei.org", "progressivepolicy.org",
    "americanprogress.org", "thirdway.org",
    "nber.org",  # working papers, not peer-reviewed
    "epi.org", "cbpp.org",
    # Healthcare advocacy / industry associations
    "phrma.org", "bio.org", "ama-assn.org",  # association newsrooms
    "amcp.org", "pcmanet.org",
    "familiesusa.org", "nationalpartnership.org",
    # Pass-11 additions (Codex pass 11)
    "seniorcarepharmacies.org",  # trade association whitepapers
    "nabp.pharmacy", "ashp.org",
})

# Pass-10 addition (BUG-M-10): US government agency domains that are
# NOT regulatory bodies but still .gov. These are T3 policy/admin
# content, not T1 primary research.
GOV_AGENCY_DOMAINS = frozenset({
    "cms.gov",        # Centers for Medicare & Medicaid Services
    "hhs.gov",        # Health & Human Services
    "cdc.gov",        # already in REGULATORY_DOMAINS but safe to list
    "va.gov",         # Veterans Affairs
    "ihs.gov",        # Indian Health Service — fact sheets not primary
    "ssa.gov",        # Social Security
    "treasury.gov", "whitehouse.gov",
    "medicare.gov", "medicaid.gov",
    "samhsa.gov",     # Substance Abuse & Mental Health
    "hrsa.gov",       # Health Resources & Services Admin
})

# I-ready-017 (#1133): national + international statistical / data agencies.
# These produce PRIMARY quantitative evidence (labour-force surveys, national
# accounts, economic data series) and are the expected T3 backbone for
# non-clinical domains such as `workforce` (config/scope_templates/workforce.yaml
# expected_tier_distribution requires T3 at 35-65%, naming StatCan / BLS / OECD
# / ILO / Eurostat explicitly).
#
# RERUN-BUG: bls.gov was demoted to T4 (OpenAlex returned preprint/repository on
# one congressional-report URL -> R11; article+journal on an MLR URL whose title
# tripped a narrative-flavor marker -> R9). oecd.org / ilo.org (.org, not on any
# domain set) fell through to UNKNOWN. Result: T3 = 0% -> abort_corpus_approval_
# denied on drb_72. These are genuine statistical agencies; T3 is the correct,
# faithfulness-safe classification (NOT T1 primary-research-paper credit — the
# clinical T3 = government/regulatory/authoritative-data tier is the right home).
#
# Eurostat note: ec.europa.eu already parent-matches `europa.eu` in
# REGULATORY_DOMAINS, so Eurostat URLs are already T3 via R2d. ec.europa.eu is
# listed here for explicitness; it is tier-harmless (both paths -> T3).
STATISTICAL_AGENCY_DOMAINS = frozenset({
    # US
    "bls.gov",                 # Bureau of Labor Statistics
    "census.gov",              # US Census Bureau
    "federalreserve.gov",      # Federal Reserve Board
    "stlouisfed.org",          # St. Louis Fed (FRED economic data series)
    "fred.stlouisfed.org",     # FRED (parent-match also covers this)
    # Canada
    "statcan.gc.ca",           # Statistics Canada
    "www150.statcan.gc.ca",    # StatCan data tables host (parent-match also)
    # International statistical / data agencies (.org / .int / .europa.eu)
    "oecd.org",                # OECD (Employment/Skills/Future of Work outlooks)
    "ilo.org",                 # International Labour Organization (+ ILOSTAT)
    "ilostat.ilo.org",         # ILOSTAT data host (parent-match also covers this)
    "ec.europa.eu",            # Eurostat lives under ec.europa.eu/eurostat
    "worldbank.org",           # World Bank Open Data
    "data.worldbank.org",      # World Bank data host (parent-match also covers)
    "imf.org",                 # International Monetary Fund
})

# Pass-10 addition (BUG-M-10): business / general news that OpenAlex
# sometimes flags as 'article' in 'journal'. These are T6 news, not
# primary research.
BUSINESS_NEWS_DOMAINS = frozenset({
    "fastcompany.com", "forbes.com", "inc.com",
    "businessinsider.com", "fortune.com", "qz.com",
    "axios.com", "thehill.com", "politico.com",
    "wired.com",  # also in NEWS_BLOG but reinforce
    # Industry-specific business news
    "beckerspayer.com", "beckershospitalreview.com",
    "modernhealthcare.com", "healthcaredive.com",
})

# Pass-10 addition (BUG-M-10): SEO/"best-X" web guides and content
# farms that rank for consumer-style queries. T6 regardless of metadata.
WEB_GUIDE_DOMAINS = frozenset({
    "chitika.com",
    "pcmag.com", "techradar.com", "zdnet.com", "cnet.com",
    "tomshardware.com", "digitaltrends.com",
    "lifewire.com", "howtogeek.com",
    "g2.com", "capterra.com", "trustradius.com",  # vendor review portals
    # Pass-11 additions (Codex pass 11)
    "emergentmind.com",  # web explainer / topic pages
    "geekwire.com", "hackernoon.com", "towardsdatascience.com",
    # Industry/trade news that OpenAlex mis-labels as journal
    "powderbulksolids.com",  # trade news
    "foodbusinessnews.com", "foodprocessing.com",
})

# R-5 Fix A: Vendor blogs / product marketing from SaaS or AI companies.
# These often rank highly in search, contain specific benchmark numbers
# (e.g., "embedding costs $0.00002 per 1K tokens"), and were escaping to
# T1/T4 via OpenAlex enrichment. Not peer-reviewed or independent.
VENDOR_BLOG_DOMAINS = frozenset({
    # RAG / ML vendors flagged in the R-3 sweep
    "morphik.ai", "glean.com", "intellectia.ai",
    "medcrypt.com", "complizen.ai", "intertek.com",
    # Other common AI/ML SaaS blogs that show up for tech queries
    "langchain.com", "llamaindex.ai", "pinecone.io",
    "weaviate.io", "anthropic.com", "openai.com",  # when scraping blog posts
    "huggingface.co",  # hub pages, not papers — but papers should come via arxiv
    # Cloud / infrastructure vendor blogs
    "databricks.com", "snowflake.com", "cloudflare.com",
    "aws.amazon.com", "cloud.google.com", "azure.microsoft.com",
    # Finance / market-research platforms posing as primary analysis
    "seekingalpha.com", "fool.com", "motleyfool.com",
    "zacks.com", "marketwatch.com",
    # Yahoo Finance / Bloomberg-hosted opinion pieces
    "finance.yahoo.com",  # articles, not primary
})

# R-5 Fix A: Self-publishing platforms. LinkedIn Pulse, Medium, Substack
# etc. were already in NEWS_BLOG_DOMAINS, but LinkedIn specifically needs
# a pulse/article subpath check because linkedin.com is also a valid
# professional profile URL. Handled in the classifier by matching the
# subdomain + path (see SELF_PUBLISH_PATH_MARKERS below).
SELF_PUBLISH_PATH_MARKERS = (
    "linkedin.com/pulse/",
    "linkedin.com/in/",  # personal profiles, rarely a research source
)

# News / blog / commentary (T6). Non-exhaustive; supplemented by
# source_type_hint == "news".
NEWS_BLOG_DOMAINS = frozenset({
    # General news
    "reuters.com", "ap.org", "apnews.com",
    "nytimes.com", "wsj.com", "ft.com", "bloomberg.com",
    "bbc.com", "bbc.co.uk", "theguardian.com",
    "cnn.com", "cnbc.com", "npr.org", "pbs.org",
    # Health / medical news
    "healthline.com", "medicalnewstoday.com", "statnews.com",
    "medscape.com", "webmd.com", "drugs.com",
    "medpagetoday.com", "healthnews.com",
    "endocrinologyadvisor.com", "rheumatologyadvisor.com",
    "oncologynursingnews.com", "cardiologyadvisor.com",
    # Pass-13 addition (Codex pass 13): pharmacytimes.com was getting
    # labelled T2 because OpenAlex lookup returned SR/MA metadata for
    # a similarly-titled review the site was reporting on. It's a
    # trade news site, not primary or secondary research.
    "pharmacytimes.com",
    # Industry / pharma trade press
    "fiercepharma.com", "biopharmadive.com", "endpts.com",
    "pharmatimes.com", "pharmamanufacturing.com",
    # Pass-9 addition: chemistry / trade news that OpenAlex sometimes
    # mis-labels as 'review'. C&EN is ACS trade press — reports ON
    # primary research but is not itself peer-reviewed research.
    "cen.acs.org", "chemistryworld.com",
    # Press-release wire services (live-run FP-2: prnewswire got tiered
    # T4 by OpenAlex because it marked it pub_type=review; wires are
    # actually commentary on primary sources and should be T6).
    "prnewswire.com", "businesswire.com", "globenewswire.com",
    "prweb.com", "prlog.org", "einpresswire.com", "marketwired.com",
    "newswire.com", "presswire.com", "pharmabiz.com",
    # Blogs / substack / medium / dev.to
    "substack.com", "medium.com", "dev.to", "blogspot.com",
    "wordpress.com",
    # Tech news (for tech-domain queries)
    "techcrunch.com", "theverge.com", "wired.com", "arstechnica.com",
    "venturebeat.com", "siliconangle.com",
    # Affiliate / content-farm markers
    "aimultiple.com", "intuitionlabs.ai", "serenitiesai.com",
})

# Peer-reviewed medical / scientific journal domains where articles
# are typically T1 (primary) or T2 (SR/MA) unless OpenAlex says
# otherwise. Venue-level hints only — not definitive on their own.
PEER_REVIEWED_JOURNAL_DOMAINS = frozenset({
    "nejm.org", "jamanetwork.com", "thelancet.com", "bmj.com",
    "nature.com", "science.org", "cell.com",
    "sciencedirect.com", "springer.com", "wiley.com",
    "onlinelibrary.wiley.com",
    "ncbi.nlm.nih.gov", "pubmed.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov",
    "frontiersin.org", "mdpi.com", "plos.org", "plosone.org",
    "ahajournals.org", "diabetesjournals.org", "endocrine.org",
    "acc.org", "acpjournals.org",
    # I-bug-771 (#812): jacc.org (J. Am. Coll. Cardiology) is a flagship
    # cardiology journal (Elsevier 10.1016) but was absent — its articles
    # demoted to T4 via the R9 unverified-host guard. acc.org alone did not
    # cover the jacc.org host.
    "jacc.org", "onlinejacc.org",
    "acs.org", "pubs.acs.org", "rsc.org", "pubs.rsc.org",
    "ieee.org", "acm.org",
    "academic.oup.com",  # OUP journals
    "cureus.com",  # peer-reviewed but low-barrier; caller should tier-down
    "bmcmedicine.com", "biomedcentral.com",
    "jme.bmj.com",  # Journal of Medical Ethics
})

# I-bug-771 (#812): low-quality / high-volume open-access publishers whose
# PRIMARY articles must NOT earn T1 (variable methodological quality), but
# whose genuine full-title systematic reviews / meta-analyses remain T2 (Codex
# #812 reconcile B — discriminator, not a hard ceiling). The primary-path
# demotion is applied in R9/R10; the SR/MA branches (which fire first) are
# untouched, preserving the deliberate pass-12 MDPI-SR/MA->T2 distinction.
LOW_QUALITY_OA_DOMAINS = frozenset({
    "mdpi.com",
})
# DOI prefixes for the same publishers (URL-embedded).
LOW_QUALITY_OA_DOI_PREFIXES = frozenset({
    "10.3390",  # MDPI
})

# I-bug-771 (#812): recognized guideline-issuing bodies. A document on one of
# these hosts whose path signals a clinical practice guideline is high-authority
# SECONDARY evidence (T2 — counts toward the clinical T2 minimum), reasoned as
# "guideline authority", explicitly NOT a primary study. Society tool / dosing /
# practice-support paths are EXCLUDED here and stay T3 (Codex #812: "acc.org
# tools/dosing PDFs do not get T1/T2"). Content stubs are unaffected — Rule 1
# returns T7 before this rule, so a 297-char fetch can never be laundered up.
GUIDELINE_AUTHORITY_DOMAINS = frozenset({
    "escardio.org",      # European Society of Cardiology
    "nice.org.uk",       # NICE (UK)
    "ahajournals.org",   # AHA/ACC guidelines published in Circulation
    "jacc.org", "onlinejacc.org",
    "acc.org",           # ACC guideline pages (NOT /tools/ — excluded below)
})
_GUIDELINE_PATH_MARKERS = (
    "/guidelines/", "/guideline/", "/guidance/", "/recommendations/",
    "/scientific-documents/recom",  # ESC scientific-documents recommendations
)
# I-bug-771 (#812) iter-2 (Codex P1): canonical ACC/AHA guidelines are published
# as DOI ARTICLES (e.g. ahajournals.org/doi/10.1161/CIR..., jacc.org/doi/...),
# NOT on a /guidelines/ path — so a path-only check misses them. On a recognized
# guideline-authority domain, these NARROW clinical-guideline title markers also
# promote to T2. Deliberately EXCLUDES the broad explainer/whitepaper/industry
# markers in _GUIDELINE_EXPLAINER_TITLE_MARKERS (those stay T4): a guideline is a
# practice/consensus/scientific statement, not a fact sheet or market insight.
# iter-4 (Codex P1+P2): distinguish an ISSUED guideline DOCUMENT from primary
# studies and from commentary ABOUT guidelines. Two robust signals:
#  (a) a year-anchored "<YYYY> ... guideline(s) for|on ..." pattern — issued
#      clinical guidelines are year-dated society documents whose title reads
#      "2021 ACC/AHA/SCAI Guideline for Coronary Artery Revascularization" /
#      "2024 ESC Guidelines for the management of AF". The phrase "guideline(s)
#      FOR/ON" (not "guideline recommendations for") + a year is the document
#      signal. This catches main-title-only forms (Codex P2: no "for the"
#      required) AND rejects undated guideline-comparison commentary like
#      "International Clinical Practice Guideline Recommendations for Acute PE:
#      Harmony, Dissonance, and Silence" (no year + "guideline recommendations
#      for", not "guideline for") (Codex P1).
#  (b) explicit document-TYPE statements that are themselves the artifact.
# Bare "guideline" / "clinical practice guideline" substrings are DELIBERATELY
# NOT markers (they appear in GDMT primaries + guideline-comparison commentary).
_GUIDELINE_DOC_STATEMENT_MARKERS = (
    "consensus statement", "expert consensus",
    "scientific statement",            # AHA scientific statements
    "position statement",
    "practice bulletin",
)
_GUIDELINE_YEAR_DOC_RE = re.compile(
    r"\b(?:19|20)\d{2}\b.{0,80}\bguidelines?\s+(?:for|on|update|focused update)\b"
)
# Primary-study / commentary titles that MENTION guidelines but are NOT
# guideline documents — never promoted (checked FIRST).
_GUIDELINE_TITLE_EXCLUSIONS = (
    "guideline-directed", "guideline directed",      # GDMT — a therapy, studied in primaries
    "guideline adherence", "guideline-adherent", "guideline adherent",
    "adherence to guideline", "adherence to the guideline",
    "guideline-concordant", "guideline concordant",
    "guideline implementation", "guideline-based", "guideline based",
    "guideline-recommended", "guideline recommended",
    "non-guideline", "off-guideline",
)
# iter-5 (Codex P1): study-ABOUT-a-document framings, anchored to the TITLE
# START. A primary study that validates / uses / evaluates a consensus statement,
# decision pathway, or guideline is NOT itself the issued document — e.g.
# "Validation of the 2019 Expert Consensus Algorithm ..." / "Validation of the
# ACC Expert Consensus Decision Pathway ...". Issued guideline/consensus
# documents START with a year or a society name (or "Clinical Practice
# Guideline" / "Expert Consensus ..."), NEVER with a study verb. Anchoring to
# the start (not substring-anywhere) avoids over-excluding real guidelines whose
# scope phrase contains a verb mid-title (e.g. "Guideline for the Evaluation of
# Chest Pain").
_STUDY_FRAMING_TITLE_PREFIXES = (
    "validation of", "validating", "a validation",
    "use of", "using", "utilization of", "utility of",
    "impact of", "implementation of", "application of",
    "evaluation of", "comparison of", "comparing",
    "association of", "association between", "predictors of",
    "outcomes of", "outcomes after", "effect of", "effects of",
    "efficacy and safety of", "efficacy of", "safety of",
    "adherence to", "real-world",
)


def _title_signals_clinical_guideline(title: str) -> bool:
    """I-bug-771 (#812): detect an ISSUED clinical-practice-guideline DOCUMENT
    title for the guideline-authority promotion in Rule 8c. Exclusions checked
    FIRST (GDMT / adherence / implementation primaries). Then a year-anchored
    "guideline(s) for|on" document pattern OR an explicit document-type statement
    (consensus / scientific / position statement / practice bulletin). Rejects
    undated guideline-comparison commentary. Narrower than
    _detect_guideline_or_explainer_title (which fires on explainer/policy titles
    that must stay T4)."""
    if not title:
        return False
    t = title.lower()
    if any(x in t for x in _GUIDELINE_TITLE_EXCLUSIONS):
        return False
    # iter-5: a study ABOUT a document (validation/use/impact/...) starts with a
    # study verb; issued documents do not. Reject these before the document
    # markers so "Validation of the ... Expert Consensus ..." is not promoted.
    t_start = t.lstrip("\"'([ ")
    if any(t_start.startswith(p) for p in _STUDY_FRAMING_TITLE_PREFIXES):
        return False
    if any(m in t for m in _GUIDELINE_DOC_STATEMENT_MARKERS):
        return True
    return bool(_GUIDELINE_YEAR_DOC_RE.search(t))

# M-18a (DR audit pass 1): when the fetcher records the URL as
# doi.org/<prefix>/<suffix>, the classifier cannot know from the
# domain alone that this is a peer-reviewed journal. These DOI
# prefixes are registered to specific peer-reviewed publishers and
# can be trusted as equivalent to PEER_REVIEWED_JOURNAL_DOMAINS
# membership. Source: Crossref registrant records.
PEER_REVIEWED_DOI_PREFIXES = frozenset({
    "10.1056",  # NEJM
    "10.1001",  # JAMA Network
    "10.1016",  # Elsevier (Lancet, Cell, Cell Metabolism, etc.)
    "10.1038",  # Nature Publishing Group
    "10.1126",  # Science / AAAS
    "10.1136",  # BMJ
    "10.1002",  # Wiley
    "10.1007",  # Springer
    "10.1111",  # Wiley
    "10.1210",  # Endocrine Society
    "10.2337",  # American Diabetes Association
    "10.1093",  # Oxford University Press
    "10.1161",  # American Heart Association
    "10.1152",  # American Physiological Society
    "10.4239",  # World Journal of Diabetes
    "10.1172",  # J Clin Invest
    "10.1059",  # Am Coll Physicians / ACP
    "10.3389",  # Frontiers
    "10.3390",  # MDPI
    "10.1371",  # PLOS
    "10.7759",  # Cureus
    "10.1080",  # Taylor & Francis
    "10.1089",  # Mary Ann Liebert
    "10.1155",  # Hindawi (peer-reviewed but mixed quality)
})


def _has_peer_reviewed_doi_prefix(url: str) -> bool:
    """Return True if URL points at a DOI with a peer-reviewed
    publisher prefix (M-18a DR audit fix)."""
    if not url:
        return False
    u = url.lower()
    if "doi.org/" not in u:
        return False
    # Extract DOI after doi.org/
    try:
        tail = u.split("doi.org/", 1)[1]
        prefix = tail.split("/", 1)[0]
        return prefix in PEER_REVIEWED_DOI_PREFIXES
    except (IndexError, ValueError):
        return False


def _is_doi_org_journal_with_venue(signals: "ClassificationSignals") -> bool:
    """F12 (GH #1245 / D12): True when a doi.org-hosted canonical DOI resolves
    to a real OpenAlex JOURNAL venue.

    THE BUG (run-killer): a canonical-DOI journal hosted on doi.org (e.g. JEP
    10.1257, JPE 10.1086) is NOT on PEER_REVIEWED_JOURNAL_DOMAINS (host is
    `doi.org`, not the publisher), and its DOI prefix may not be in the
    hard-coded PEER_REVIEWED_DOI_PREFIXES allowlist. R9's unverified-host guard
    then demotes it to T4. ~50 such sources fell to T4 on the workforce corpus,
    collapsing the resolved-venue tier and false-firing abort_corpus_inadequate.

    THE FIX: instead of whack-a-mole prefix expansion, TRUST the resolved
    OpenAlex venue. A doi.org host with OpenAlex `source_type == "journal"` AND
    a non-empty venue name IS a peer-reviewed journal — count it as such rather
    than defaulting to the doi.org-host prior. This widens R9's unverified-host
    EXEMPTION only; it never relaxes a faithfulness gate and is scoped strictly
    to doi.org-hosted canonical DOIs so the BUG-M-11 trade-content guard on
    non-DOI hosts is untouched. SR/MA, narrative, guideline, conference-abstract
    and low-quality-OA branches all run BEFORE / AFTER this exemption and still
    win (e.g. a doi.org/10.3390 MDPI work still hits _is_low_quality_oa -> T4).

    Scope is enforced on the PARSED HOST (host == doi.org or *.doi.org, e.g.
    dx.doi.org), NOT a substring of the URL — a non-doi.org trade host that
    embeds `doi.org/` in its path or query (e.g.
    `https://trade.example/redirect/https://doi.org/10.x`) must NOT pass, so the
    BUG-M-11 trade-content guard stays intact (Codex diff-gate iter-1 P1).
    """
    host = _normalize_domain(signals.url)
    if not (host == "doi.org" or host.endswith(".doi.org")):
        return False
    src_type = (signals.openalex_source_type or "").strip().lower()
    venue = (signals.openalex_venue or "").strip()
    return src_type == "journal" and bool(venue)


def _is_low_quality_oa(domain: str, url: str) -> bool:
    """I-bug-771 (#812): True if the source is a low-quality / high-volume OA
    publisher (MDPI) by domain OR by URL-embedded DOI prefix. Used to deny T1
    primary credit in R9/R10 (SR/MA still routes to T2 in the earlier branch)."""
    if _domain_matches(domain, LOW_QUALITY_OA_DOMAINS):
        return True
    u = (url or "").lower()
    # Exact DOI-prefix match (iter-2 Codex P2: avoid substring false-positives
    # such as 10.33901 matching 10.3390). Extract the registrant prefix after
    # doi.org/ exactly, mirroring _has_peer_reviewed_doi_prefix.
    if "doi.org/" in u:
        try:
            prefix = u.split("doi.org/", 1)[1].split("/", 1)[0]
            if prefix in LOW_QUALITY_OA_DOI_PREFIXES:
                return True
        except (IndexError, ValueError):
            pass
    # DOI embedded in a publisher path (e.g. /10.3390/...): require both
    # boundary slashes so 10.33901 cannot match 10.3390.
    return any(f"/{p}/" in u for p in LOW_QUALITY_OA_DOI_PREFIXES)


# Preprint servers (T4/T5 candidates — not peer-reviewed; caller may
# tier-down further based on funding disclosure).
PREPRINT_DOMAINS = frozenset({
    "arxiv.org", "biorxiv.org", "medrxiv.org", "ssrn.com",
    "preprints.org", "researchsquare.com", "papers.ssrn.com",
    "osf.io",
})

# Student-journal / low-credibility-journal patterns. Plan A-S3-A note
# flagged nhsjs.com (National High School Journal of Science) as
# inappropriately tagged GOLD in PG_LB_SA_02. These are not predatory
# per se but don't meet T1/T2 peer-review standards.
STUDENT_JOURNAL_DOMAINS = frozenset({
    "nhsjs.com",
})

# Abstract-only / stub-content domains where typical content is just a
# title + abstract. Used as a hint; falls through to content-length check.
ABSTRACT_ONLY_DOMAINS = frozenset({
    "semanticscholar.org",
    "openalex.org",
})

# Content-length thresholds (chars of fetched body).
MIN_T1_T4_CONTENT_CHARS = 3000  # below this, downgrade to T7 stub
T7_STUB_CONTENT_CHARS = 1000    # below this, always T7 stub


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_domain(url: str) -> str:
    """Extract lowercase domain from URL, stripping www. and path."""
    if not url:
        return ""
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        host = (parsed.hostname or "").lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _domain_matches(domain: str, domain_set: frozenset[str]) -> bool:
    """Check whether domain (or any parent) is in the set."""
    if not domain:
        return False
    if domain in domain_set:
        return True
    # Parent-domain match: foo.fda.gov matches fda.gov
    parts = domain.split(".")
    for i in range(len(parts)):
        parent = ".".join(parts[i:])
        if parent in domain_set:
            return True
    return False


def _detect_systematic_review_from_title(title: str) -> bool:
    """Heuristic: title contains 'systematic review' / 'meta-analysis'."""
    if not title:
        return False
    t = title.lower()
    return any(k in t for k in (
        "systematic review", "meta-analysis", "meta analysis",
        "network meta-analysis", "cochrane review", "umbrella review",
        "scoping review",
    ))


def _detect_narrative_review_from_title(title: str) -> bool:
    """Heuristic: title contains 'review' but not systematic / meta."""
    if not title:
        return False
    t = title.lower()
    if "review" in t and not _detect_systematic_review_from_title(title):
        return True
    # Commentary / editorial / perspective markers
    return any(k in t for k in (
        "commentary", "editorial", "perspective", "opinion",
        "viewpoint",
    ))


def _detect_conference_abstract(title: str, url: str = "") -> bool:
    """Heuristic: title / URL signals a conference abstract.

    Matches:
    - explicit keywords (conference abstract, poster, oral presentation)
    - "1745-P:" / "82-OR:" / "P-123:" abstract-number prefixes commonly
      used by ADA, ENDO, ESC, etc.
    - Pass-16 (Codex full-scale pass 1): Endocrine Society / ENDO
      day-prefixed presentation IDs like "THU296" / "MON-123" / "FRI42"
      / "SAT-56" / "SUN-78" that prefix supplement abstracts.
    - URLs containing "/Supplement_" or "/abstract/" or journal-issue
      supplement paths, or "/jes/article-pdf/.../Supplement_"
    """
    if title:
        t = title.lower()
        if any(k in t for k in (
            "conference abstract", "poster", "oral presentation",
            "abstract p", "abstract po",
        )):
            return True
        # Numbered abstract prefix (e.g., "1745-P: Long-Term Safety...")
        if re.match(r"^\s*\d+-[A-Z]+:", title):
            return True
        # Numbered "P-" prefix
        if re.match(r"^\s*P-\d+", title):
            return True
        # Pass-16 (Codex full-scale pass 1): Endocrine Society day-letter
        # presentation IDs. Pattern: MON/TUE/WED/THU/FRI/SAT/SUN + 2-4
        # digits, optionally with hyphen. Must be at title start.
        if re.match(
            r"^\s*(MON|TUE|WED|THU|FRI|SAT|SUN)-?\d{2,4}\b",
            title, re.IGNORECASE,
        ):
            return True
        # Pass-16: abstract-ID-like prefixes commonly seen on JES/JCEM
        # supplements, e.g., "OR01-2", "OR30-04", "SUN-245"
        if re.match(r"^\s*OR\d+-\d+\b", title, re.IGNORECASE):
            return True
    if url:
        u = url.lower()
        if "/supplement_" in u or "/supplement/" in u:
            return True
        # Pass-16: "/jes/article-pdf/.../Supplement_1/..." pattern
        if "/article-pdf/" in u and "supplement" in u:
            return True
    return False


# Narrative-review / commentary-flavored keywords. Broader than the
# "systematic review" family. Surfaces commentary-ish articles in
# peer-reviewed venues (J Obes Metab Syndr, Postgraduate Med, etc.).
# M-18a (DR audit pass 1): STRONG narrative markers — always fire
# regardless of primary-study signals. These phrases unambiguously
# indicate that the paper is NOT a primary RCT even if it references
# one (e.g., post-hoc analyses of a SURPASS trial ARE narrative).
_NARRATIVE_FLAVOR_STRONG_MARKERS = (
    # Case reports / series — always narrative regardless of primary terms
    "case report", "case reports", "case study",
    "a case of", "a case report",
    # Secondary / post-hoc analyses — always narrative; the primary
    # paper is the parent RCT, not the post-hoc report
    "post hoc", "post-hoc", "post hoc analysis", "post-hoc analysis",
    "secondary analysis",
    "pooled analysis",
    "subgroup analysis",
    # Program-level pooled reporting — still narrative
    "in the step program", "in the step programme",
    "in the surpass program", "in the surmount program",
    "in the rewind program", "in the leader program",
    "in the sustain program", "in the pioneer program",
    "in the select program",
    # M-18c (Codex pass 10 advisory): narrative framings about
    # randomized trials are reviews ABOUT RCTs, not RCTs themselves.
    # These must fire even when the title also contains "randomized".
    "beyond randomized", "beyond rcts",
    "update on randomized", "update on rcts",
    "the role of randomized", "role of randomized",
    "interpreting randomized", "interpreting rcts",
    "overview of randomized", "overview of rcts",
)

# M-18a: WEAK narrative markers — defer to primary-study signals when
# present. These phrases can appear in both narrative reviews AND in
# primary RCT titles (e.g., NEJM "X as Compared with Y for the
# Treatment of Z" uses "for the treatment of" as a study population
# delimiter, not as a narrative frame).
_NARRATIVE_FLAVOR_WEAK_MARKERS = (
    "a game changer", "game-changer", "game changer",
    "update on ", "the role of ",
    "overview of ", "advances in ",
    "a review of ",
    "the upcoming", "the coming", "on the horizon",
    "perspectives on", "viewpoints on",
    "against obesity", "for obesity",
    "for the treatment of", "for the management of",
    "perspective for", "perspective on ", "a perspective",
    "perspectives for",
    "primary care providers", "primary care physician",
    "for clinicians", "for physicians",
    "prescribing ",
    "what the clinician", "what clinicians",
)

# Preserve the combined tuple for backwards compatibility with any
# downstream code that imports _NARRATIVE_FLAVOR_KEYWORDS directly.
_NARRATIVE_FLAVOR_KEYWORDS = (
    _NARRATIVE_FLAVOR_STRONG_MARKERS + _NARRATIVE_FLAVOR_WEAK_MARKERS
)


def _detect_narrative_flavor_from_title(title: str) -> bool:
    """Stronger-than-generic detector for narrative / commentary flavor.

    M-18a (DR audit pass 1): split narrative markers into STRONG (case
    report, post-hoc analysis, pooled analysis, program-level) and
    WEAK (for the treatment of, update on, perspective for). Strong
    markers always fire. Weak markers defer to primary-study signals
    so NEJM head-to-head RCTs like "Tirzepatide as Compared with
    Semaglutide for the Treatment of Obesity" are not demoted.
    """
    if not title:
        return False
    t = title.lower()
    if _detect_narrative_review_from_title(title):
        return True
    # STRONG narrative markers fire regardless of primary-study signals.
    if any(k in t for k in _NARRATIVE_FLAVOR_STRONG_MARKERS):
        return True
    # WEAK markers defer to primary-study signals.
    if _detect_primary_study_signal(title):
        return False
    return any(k in t for k in _NARRATIVE_FLAVOR_WEAK_MARKERS)


# Pass-10 addition (BUG-M-10): title markers that indicate guideline,
# explainer, or policy-brief content even when OpenAlex says the host
# is a journal (e.g., PMC hosting a policy paper titled "Predetermined
# Change Control Plans: Guiding Principles" or a guideline titled
# "2025 Guidelines for direct oral anticoagulants"). These are T4
# narrative / analytical content, not T1 primary studies.
_GUIDELINE_EXPLAINER_TITLE_MARKERS = (
    "guideline", "guidelines",
    "guiding principle", "guiding principles",
    "key facts", "fact sheet", "fact-sheet",
    "issue brief", "policy brief",
    "explainer",
    "chartbook", "dashboard",
    "primer on",
    "introduction to",
    # "Q&A:" / "Frequently asked" style
    "q&a:", "frequently asked",
    # Government/regulator briefing language
    "agency overview", "program overview",
    # Policy explainer prefix
    "what is ", "what are ",
    "how does ", "how do ",
    # Pass-11 additions (Codex pass 11): industry insight, whitepaper,
    # checklist, early-impacts language
    "whitepaper", "white paper", "white-paper",
    "checklist",
    "early impacts", "early impact",
    "industry report", "industry insight", "industry insights",
    "market insight", "market insights",
    "pricing trends", "pricing trend",
    "case study",  # can be primary but often is narrative; over-demote OK
    # Pass-15 additions (Codex pass 15): biomedical guidance / consensus
    "guidance", "practical guidance", "clinical guidance",
    "consensus", "consensus statement", "expert consensus",
    "practice guide", "practice bulletin", "practice recommendation",
    "clinical overview", "clinical summary",
    "position statement", "position paper",
)


def _detect_guideline_or_explainer_title(title: str) -> bool:
    """Return True if the title signals guideline / explainer / policy-
    brief content. Used by R9 to demote T1 for titles that OpenAlex
    classified as 'article' in 'journal' but whose content is
    clinical-practice guidance or policy analysis, not primary research.
    """
    if not title:
        return False
    t = title.lower()
    return any(k in t for k in _GUIDELINE_EXPLAINER_TITLE_MARKERS)


# M-17f (Codex pass 7 structural pivot): gate R8b body override.
# The body-inspection detector cannot reliably disambiguate primary
# papers citing external guidelines from new guidelines citing prior
# ones. Passes 3-7 chased the regex tail without converging. Solution:
# body-signal override only fires when the title is NOT already
# diagnostic. When the title already carries article-type evidence,
# we trust the title (R9/R10 path) and log the body signal as
# advisory.
_DIAGNOSTIC_TITLE_ARTICLE_TYPE_KEYWORDS = (
    # SR/MA keywords
    "systematic review", "meta-analysis", "meta analysis",
    "network meta-analysis", "cochrane review", "umbrella review",
    "scoping review", "rapid review",
    # Case report / case series
    "case report", "case-report",
    "case series", "case-series",
    "a case of ", "report of a case",
    # Guideline / consensus / statement
    "clinical practice guideline", "practice guideline",
    "consensus statement", "consensus recommendation",
    "position statement", "expert consensus",
    # Perspective / commentary / editorial
    "perspective:", "commentary:", "editorial:",
    "opinion:", "viewpoint:",
    "letter to the editor",
    # Conference abstract markers in title
    " abstract ", "[abstract]", "(abstract)",
    # Narrative review
    "narrative review", "scoping review", "umbrella review",
    "literature review",
)


def _title_is_diagnostic_for_article_type(title: str) -> bool:
    """Return True if the title already contains explicit article-type
    evidence (systematic review, case report, guideline, etc.).

    Used by R8b to decide whether the body-inspection signal should
    override the title-based classification. When the title is
    diagnostic, we trust R9/R10 and relegate the body signal to
    advisory; when the title is non-diagnostic (truncated, generic,
    bare product name), the body signal remains the primary override.
    """
    if not title:
        return False
    t = title.lower()
    return any(k in t for k in _DIAGNOSTIC_TITLE_ARTICLE_TYPE_KEYWORDS)


# Pass-12 addition (BUG-M-12, Codex pass 12): positive primary-study
# signals. R9_openalex_primary_study previously granted T1 on any
# allowlisted journal host when OpenAlex said article+journal. Codex
# found that truncated Serper snippet titles hid SR/MA suffixes, so
# real meta-analyses (MDPI + Frontiers tirzepatide papers) slipped
# through to T1. Codex recommendation: require at least one positive
# primary-study marker before granting T1, not just absence of
# SR/MA/narrative markers.
_PRIMARY_STUDY_TITLE_MARKERS = (
    # Randomized / controlled trial markers
    "randomized", "randomised",
    "controlled trial", "controlled-trial",
    "rct",
    "double-blind", "double blind",
    "single-blind", "single blind",
    "placebo-controlled", "placebo controlled",
    # M-18a (DR audit pass 1): NEJM head-to-head RCTs often use the
    # "X as Compared with Y" formula (e.g. "Tirzepatide as Compared
    # with Semaglutide for the Treatment of Obesity"). Without this
    # marker, the "for the treatment of" narrative-flavor keyword
    # wins and the primary RCT is demoted to T4.
    "as compared with", "as compared to",
    # Phase markers (clinical)
    "phase 1", "phase 2", "phase 3", "phase 4",
    "phase i ", "phase ii ", "phase iii ", "phase iv ",
    "phase-1", "phase-2", "phase-3", "phase-4",
    # Specific named trials / acronyms that unambiguously name a study
    "surpass-", "surmount-", "step ", "select trial",
    "leader trial", "sustain trial", "rewind trial", "pioneer ",
    # Observational study markers
    "cohort study", "cohort-study",
    "case-control", "case control",
    "cross-sectional",
    "prospective study", "retrospective study",
    "observational study",
    "registry analysis", "registry-based",
    "longitudinal study",
    "post-marketing surveillance", "post marketing surveillance",
    "real-world evidence study", "real-world data study",
    # Primary lab / mechanism markers (for tech/bench research)
    "effect of ", "effects of ",  # "Effect of X on Y" pattern
    # Explicit "trial"
    " trial:", " trial of ", " a trial ",
    "first-in-human", "first in human",
)


def _detect_primary_study_signal(title: str) -> bool:
    """Return True if the title contains a positive primary-research
    signal (randomized trial, cohort study, named phase trial, etc.).
    Used by R9 to require positive evidence before granting T1 —
    merely passing OpenAlex article+journal is not enough.
    """
    if not title:
        return False
    t = title.lower()
    return any(k in t for k in _PRIMARY_STUDY_TITLE_MARKERS)


# ─────────────────────────────────────────────────────────────────────────────
# The classifier
# ─────────────────────────────────────────────────────────────────────────────

def classify_source_tier(
    signals: ClassificationSignals,
) -> ClassificationResult:
    """Drop-in dispatcher (Phase 0a, GH #983) — the ONLY switch point.

    OFF (default): returns the byte-identical legacy rule body.
    ON  (PG_USE_AUTHORITY_MODEL in {1,true,yes}): computes the field-agnostic
        authority result, renders the clinical T1-T7 VIEW, and returns a
        ClassificationResult with the SAME five legacy fields populated PLUS
        the four additive authority fields. No downstream consumer reads the
        authority fields in 0a — shadow only.
    """
    if os.getenv("PG_USE_AUTHORITY_MODEL", "0").lower() in ("1", "true", "yes"):
        return _classify_via_authority_model(signals)
    return _classify_source_tier_rules(signals)


def _classify_source_tier_rules(
    signals: ClassificationSignals,
) -> ClassificationResult:
    """Classify a source into T1-T7 (or UNKNOWN) using rules.

    Rules fire in priority order. The first match wins; later rules
    cannot overturn an earlier decision (so rule ordering is
    load-bearing). Every match appends to result.reasons so the user
    can audit why a tier was assigned.

    Returns TierLevel.UNKNOWN rather than silent BRONZE when no rule
    matches — see module docstring for rationale.
    """
    result = ClassificationResult(
        tier=TierLevel.UNKNOWN,
        confidence=0.0,
    )
    domain = _normalize_domain(signals.url)
    result.signals_used = {
        "domain": domain,
        "source_type_hint": signals.source_type_hint,
        "publication_type": signals.openalex_publication_type,
        "content_length": signals.fetched_content_length,
    }

    # ── Rule 0 (BLOCKED): Retracted papers are never classified positively
    if signals.openalex_is_retracted:
        result.tier = TierLevel.UNKNOWN  # caller should exclude; not T1-T7
        result.confidence = 1.0
        result.matched_rules.append("R0_retracted")
        result.reasons.append(
            "Paper flagged retracted by OpenAlex; excluded from tier scoring. "
            "Caller should filter retracted sources before composition."
        )
        return result

    # ── Rule Pre-1 (T6, M-18b from DR audit pass 1): Social platform
    # / general-interest portal exclusion. Must fire BEFORE R1 stub-
    # content so that Facebook/Twitter/Reddit pages are classified by
    # domain authority, not by how much text happened to be fetched.
    # A Facebook "Black Box Warning" post is not more citable just
    # because its body happens to be > 1000 chars.
    if _domain_matches(domain, SOCIAL_PLATFORM_DOMAINS):
        result.tier = TierLevel.T6
        result.confidence = 0.98
        result.matched_rules.append("RP1_social_platform_early")
        result.reasons.append(
            f"Domain {domain!r} is a social platform / general-interest "
            f"portal. User-generated or aggregator content; never T1 "
            f"primary research regardless of content length or OpenAlex "
            f"metadata. M-18b: fires BEFORE R1 stub so tier cannot be "
            f"laundered via large body text."
        )
        return result

    # ── Rule 1 (T7 stub): Tiny content = stub regardless of venue
    # This runs early because even a JAMA paper fetched as 500-char
    # abstract is effectively a stub for evaluator purposes.
    if signals.fetched_content_length and signals.fetched_content_length < T7_STUB_CONTENT_CHARS:
        result.tier = TierLevel.T7
        result.confidence = 1.0
        result.matched_rules.append("R1_stub_content_length")
        result.reasons.append(
            f"Fetched body is {signals.fetched_content_length} chars "
            f"(< {T7_STUB_CONTENT_CHARS} threshold) — classified T7 stub "
            f"regardless of venue. Full-text retrieval would be needed "
            f"to upgrade."
        )
        return result

    # ── Rule 2a (T6): Low-provenance document hosts. A government PDF
    # re-hosted on Scribd has unknown authenticity; do NOT elevate to T3
    # just because source_type_hint says "government_report". This fires
    # before the regulatory rule specifically to catch laundering.
    if _domain_matches(domain, LOW_PROVENANCE_HOSTS):
        result.tier = TierLevel.T6
        result.confidence = 0.95
        result.matched_rules.append("R2a_low_provenance_host")
        result.reasons.append(
            f"Domain {domain!r} is a user-upload document host with no "
            f"provenance guarantees. T6 regardless of upstream metadata "
            f"hints; the authentic source should be located at the "
            f"original issuer's URL."
        )
        return result

    # ── Rule 2b (T6): Legal / consulting commentary
    if _domain_matches(domain, LEGAL_COMMENTARY_DOMAINS):
        result.tier = TierLevel.T6
        result.confidence = 0.95
        result.matched_rules.append("R2b_legal_commentary")
        result.reasons.append(
            f"Domain {domain!r} is a law-firm or legal-commentary site. "
            f"Not peer-reviewed research. T6."
        )
        return result

    # ── Rule 2b-social (T6, BUG-M-7): Social platforms + general-interest
    # portals. Per Codex pass 9 findings, Facebook / Reddit / AOL pages
    # were being classified as T1 via OpenAlex because those domains
    # sometimes appear as journal source_type in upstream metadata.
    # User-generated content and aggregator portals are never T1.
    if _domain_matches(domain, SOCIAL_PLATFORM_DOMAINS):
        result.tier = TierLevel.T6
        result.confidence = 0.95
        result.matched_rules.append("R2b_social_platform")
        result.reasons.append(
            f"Domain {domain!r} is a social platform or general-interest "
            f"portal. User-generated or aggregator content; never T1 "
            f"primary research regardless of OpenAlex metadata."
        )
        return result

    # ── Rule 2b-market (T5/T6, BUG-M-7): Market research / consulting.
    # Per Codex pass 9, DelveInsight / Statista / MatrixBCG /
    # PortersFiveForce / PharmaVoice were being classified T1 via
    # OpenAlex. These are paid industry analyses — typically T5 when
    # they're primary market research, T6 when they're strategy-blog
    # summaries. Tier at T5 by default (industry-funded) because most
    # specific reports cited in POLARIS runs are paid research, not
    # vendor marketing collateral.
    if _domain_matches(domain, MARKET_RESEARCH_DOMAINS):
        result.tier = TierLevel.T5
        result.confidence = 0.9
        result.matched_rules.append("R2b_market_research")
        result.reasons.append(
            f"Domain {domain!r} is a market-research / consulting firm. "
            f"Paid industry analysis, not peer-reviewed research. T5."
        )
        return result

    # ── Rule 2b-clinref (T4, BUG-M-10): Clinical reference products.
    # UpToDate, DynaMed, ClinicalKey, BMJ Best Practice, etc. are
    # clinical decision-support summaries. Useful for practitioners
    # but not primary research. Tier at T4 (narrative / commentary).
    if _domain_matches(domain, CLINICAL_REFERENCE_PRODUCTS):
        result.tier = TierLevel.T4
        result.confidence = 0.9
        result.matched_rules.append("R2b_clinical_reference_product")
        result.reasons.append(
            f"Domain {domain!r} is a clinical reference product (UpToDate "
            f"/ DynaMed / etc.). Practitioner-oriented decision-support "
            f"summaries of existing evidence, not primary research. T4."
        )
        return result

    # ── Rule 2b-policy (T4, BUG-M-10): Policy think-tanks / advocacy.
    # KFF, Commonwealth Fund, Brookings, Rand, PhRMA, etc. produce
    # policy analyses, explainers, and advocacy content. Useful
    # references but not peer-reviewed primary research. Tier at T4
    # as narrative analysis by default.
    if _domain_matches(domain, POLICY_THINK_TANK_DOMAINS):
        result.tier = TierLevel.T4
        result.confidence = 0.85
        result.matched_rules.append("R2b_policy_think_tank")
        result.reasons.append(
            f"Domain {domain!r} is a policy think-tank / advocacy / "
            f"trade-association site. Policy analysis or explainer "
            f"content, not peer-reviewed primary research. T4."
        )
        return result

    # ── Rule 2b-gov-agency (T3, BUG-M-10): non-regulatory government
    # agency content. CMS.gov, HHS.gov etc. produce administrative,
    # policy, and fact-sheet content. T3 government/regulatory is
    # correct here — but crucially NOT T1 primary research via
    # OpenAlex metadata misclassification.
    if _domain_matches(domain, GOV_AGENCY_DOMAINS):
        result.tier = TierLevel.T3
        result.confidence = 0.95
        result.matched_rules.append("R2b_gov_agency")
        result.reasons.append(
            f"Domain {domain!r} is a US government agency (non-regulatory). "
            f"Administrative / policy / fact-sheet content, not primary "
            f"research. T3."
        )
        return result

    # ── Rule 2b-stat-agency (T3, I-ready-017 #1133): national +
    # international statistical / data agencies (BLS, OECD, ILO, Eurostat,
    # StatCan, World Bank, IMF, Federal Reserve, FRED, Census). These
    # produce PRIMARY quantitative evidence and are the expected T3
    # backbone for non-clinical domains (workforce protocol requires
    # T3 at 35-65%). Placed adjacent to R2b_gov_agency / R2c / R2d so
    # statistical agencies earn T3 the same way regulatory domains do,
    # and crucially BEFORE R9/R10/R11 (the OpenAlex paths that demoted
    # bls.gov to T4) and AFTER the R2a/R2b denylist demotions (so a
    # denylisted domain can never be laundered up to T3). It is T3
    # (government/regulatory/authoritative-data tier), NOT T1 primary-
    # research-paper credit.
    if _domain_matches(domain, STATISTICAL_AGENCY_DOMAINS):
        result.tier = TierLevel.T3
        result.confidence = 0.95
        result.matched_rules.append("R2b_statistical_agency")
        result.reasons.append(
            f"Domain {domain!r} is a national or international statistical / "
            f"data agency (e.g. BLS, OECD, ILO, Eurostat, StatCan, World "
            f"Bank, IMF, Federal Reserve, Census). Authoritative primary "
            f"quantitative evidence — T3 regardless of OpenAlex metadata "
            f"(which mis-labelled BLS reports as preprint/repository or "
            f"narrative review). Not T1 primary-research-paper credit."
        )
        return result

    # ── Rule 2b-bizness (T6, BUG-M-10): Business / general news.
    # Fast Company, Forbes, etc. When OpenAlex mis-labels them as
    # 'article'/'journal', they should still be T6 news.
    if _domain_matches(domain, BUSINESS_NEWS_DOMAINS):
        result.tier = TierLevel.T6
        result.confidence = 0.95
        result.matched_rules.append("R2b_business_news")
        result.reasons.append(
            f"Domain {domain!r} is a business / general news publisher. "
            f"Not peer-reviewed research. T6."
        )
        return result

    # ── Rule 2b-webguide (T6, BUG-M-10): SEO / web-guide content.
    # Chitika, PCMag, etc. Consumer-style "best X of year" articles.
    if _domain_matches(domain, WEB_GUIDE_DOMAINS):
        result.tier = TierLevel.T6
        result.confidence = 0.95
        result.matched_rules.append("R2b_web_guide")
        result.reasons.append(
            f"Domain {domain!r} is an SEO / consumer web-guide site. T6."
        )
        return result

    # ── Rule 2c (T3): Industry-hosted regulatory content (product
    # monographs, prescribing information) — overrides industry-marketing
    # classification because the CONTENT is a regulatory-approved label
    # even though the HOSTING is manufacturer-controlled.
    _url_lower = (signals.url or "").lower()
    _title_lower = (signals.title or "").lower()
    _regulatory_content_markers = (
        "product-monograph", "product_monograph",
        "prescribing-information", "prescribing_information",
        "215256s",  # FDA label revision pattern
    )
    _regulatory_title_markers = (
        "product monograph", "prescribing information",
    )
    if any(m in _url_lower for m in _regulatory_content_markers) or \
       any(m in _title_lower for m in _regulatory_title_markers):
        result.tier = TierLevel.T3
        result.confidence = 0.9
        result.matched_rules.append("R2c_regulatory_content_marker")
        result.reasons.append(
            "URL or title contains regulatory-content marker (product "
            "monograph / prescribing information / FDA label revision "
            "pattern). T3 regardless of hosting domain."
        )
        return result

    # ── Rule 2d (T3): Regulatory domains
    if _domain_matches(domain, REGULATORY_DOMAINS):
        result.tier = TierLevel.T3
        result.confidence = 1.0
        result.matched_rules.append("R2d_regulatory_domain")
        result.reasons.append(
            f"Domain {domain!r} matches regulatory body list. "
            f"T3 regulatory/government source."
        )
        return result

    # ── Rule 3 (T5): Pharmaceutical-industry HCP portals / brand sites
    # (This fires BEFORE peer-reviewed-journal rule because some pharma
    # companies host their own pseudo-journal content.)
    if _domain_matches(domain, INDUSTRY_MARKETING_DOMAINS):
        result.tier = TierLevel.T5
        result.confidence = 1.0
        result.matched_rules.append("R3_industry_marketing_domain")
        result.reasons.append(
            f"Domain {domain!r} is a pharmaceutical-industry HCP portal or "
            f"brand site. Industry marketing material — T5 regardless of "
            f"OpenAlex indexing. (Peer-reviewed papers from the same "
            f"company published in a journal should be cited via the "
            f"journal URL, where they classify to T1/T2/T4.)"
        )
        return result

    # ── Rule 3b (T5): Branded physician-portal commentary (touchX, medscape)
    if _domain_matches(domain, PHYSICIAN_PORTAL_COMMENTARY_DOMAINS):
        result.tier = TierLevel.T5
        result.confidence = 0.9
        result.matched_rules.append("R3b_physician_portal_commentary")
        result.reasons.append(
            f"Domain {domain!r} is a branded physician-portal commentary "
            f"site (CME + sponsored content, not peer-reviewed primary "
            f"research). T5 industry-adjacent."
        )
        return result

    # ── Rule 4 (T6): News / blog domains
    if _domain_matches(domain, NEWS_BLOG_DOMAINS):
        result.tier = TierLevel.T6
        result.confidence = 1.0
        result.matched_rules.append("R4_news_blog_domain")
        result.reasons.append(
            f"Domain {domain!r} is a news / blog / commentary source. T6."
        )
        return result

    # ── Rule 4a (T5): Vendor / SaaS product blogs. R-5 Fix A.
    # These domains appear in search results for tech/policy queries
    # with specific benchmark numbers that look authoritative but are
    # product marketing. Tier T5 (industry) not T1 primary.
    if _domain_matches(domain, VENDOR_BLOG_DOMAINS):
        result.tier = TierLevel.T5
        result.confidence = 0.95
        result.matched_rules.append("R4a_vendor_blog_domain")
        result.reasons.append(
            f"Domain {domain!r} is a vendor / SaaS product blog. "
            f"Benchmark numbers and product claims originate from the "
            f"vendor; treat as industry-adjacent (T5), not peer-reviewed."
        )
        return result

    # ── Rule 4b (T6): Self-publishing platforms with a path marker.
    # LinkedIn pulse articles, personal Medium pages etc. R-5 Fix A.
    url_lower = (signals.url or "").lower()
    if any(m in url_lower for m in SELF_PUBLISH_PATH_MARKERS):
        result.tier = TierLevel.T6
        result.confidence = 0.9
        result.matched_rules.append("R4b_self_publish_path")
        result.reasons.append(
            f"URL {signals.url!r} matches a self-publishing path marker "
            f"(LinkedIn Pulse, personal profile). T6 commentary."
        )
        return result

    # ── Rule 5: source_type_hint dominates when caller knows what it has
    hint = (signals.source_type_hint or "").strip().lower()
    hint_to_tier: dict[str, TierLevel] = {
        "government_report": TierLevel.T3,
        "industry_report": TierLevel.T5,
        "news": TierLevel.T6,
        "news_blog": TierLevel.T6,
        "blog": TierLevel.T6,
        "commercial": TierLevel.T6,
        "marketing": TierLevel.T5,
        "opinion": TierLevel.T6,
        "affiliate": TierLevel.T6,
        "sponsored": TierLevel.T6,
    }
    if hint in hint_to_tier:
        result.tier = hint_to_tier[hint]
        result.confidence = 0.9
        result.matched_rules.append(f"R5_source_type_hint:{hint}")
        result.reasons.append(
            f"Upstream source_type hint {hint!r} -> {result.tier.value}"
        )
        return result

    # ── Rule 6 (T7): Abstract-only domain stubs
    if _domain_matches(domain, ABSTRACT_ONLY_DOMAINS):
        result.tier = TierLevel.T7
        result.confidence = 0.95
        result.matched_rules.append("R6_abstract_only_domain")
        result.reasons.append(
            f"Domain {domain!r} typically serves abstracts/stubs only "
            f"without full-text retrieval. T7."
        )
        return result

    # ── Rule 7: Preprint servers (T4 — not peer-reviewed yet)
    if _domain_matches(domain, PREPRINT_DOMAINS):
        result.tier = TierLevel.T4
        result.confidence = 0.9
        result.matched_rules.append("R7_preprint_domain")
        result.reasons.append(
            f"Domain {domain!r} is a preprint server. Not peer-reviewed "
            f"(yet); T4 narrative/unreviewed."
        )
        return result

    # ── Rule 8: Student-journal domains (T4 ceiling at best; often T6)
    if _domain_matches(domain, STUDENT_JOURNAL_DOMAINS):
        result.tier = TierLevel.T6
        result.confidence = 0.95
        result.matched_rules.append("R8_student_journal_domain")
        result.reasons.append(
            f"Domain {domain!r} is a student-authored journal — does not "
            f"meet peer-review standards for T1/T2. T6."
        )
        return result

    # ── Rule 8c (I-bug-771 #812): recognized guideline-issuing bodies. Fires
    # AFTER Rule 1 stub (so 297-char fetches stay T7, never laundered) and
    # BEFORE R8b/R9/R10 (so it pre-empts both the body-signal demotion AND the
    # R9 OpenAlex-article path that was granting society tool PDFs T1). Two
    # outcomes on these domains:
    #   * society tool / dosing / practice-support path  -> T3 (clinical
    #     decision-support reference; Codex #812: never T1/T2)
    #   * clinical-practice-guideline / recommendation path -> T2 (high-
    #     authority secondary evidence; "guideline authority" NOT primary)
    # A plain research article on these hosts (no tool/guideline path marker)
    # falls through to the normal journal path (R9/R10) and tiers as usual.
    # (NICE is matched here for documentation, but nice.org.uk is in
    # REGULATORY_DOMAINS and R2d already returned T3 above — a defensible
    # government/HTA classification; flagged for Codex in the diff review.)
    _gl_url = (signals.url or "").lower()
    _society_tool_path_markers = (
        "/tools/", "/tool/", "/practice-support/", "/practice-resources/",
        "/information-graphics/", "/infographic", "/dosing/", "-dosing-",
        "/clinical-tools/", "tools-and-practice-support",
    )
    if _domain_matches(domain, GUIDELINE_AUTHORITY_DOMAINS):
        if any(m in _gl_url for m in _society_tool_path_markers):
            result.tier = TierLevel.T3
            result.confidence = 0.85
            result.matched_rules.append("R8c_society_tool_demoted")
            result.reasons.append(
                f"Domain {domain!r} is a professional-society host and the URL "
                f"path matches a tool / dosing / practice-support pattern. "
                f"Clinical decision-support reference, not primary research or "
                f"a guideline document. T3 (never T1/T2 per #812)."
            )
            return result
        if (
            (
                any(m in _gl_url for m in _GUIDELINE_PATH_MARKERS)
                or _title_signals_clinical_guideline(signals.title)
            )
            and not _detect_conference_abstract(signals.title, signals.url)
        ):
            result.tier = TierLevel.T2
            result.confidence = 0.85
            result.matched_rules.append("R8c_guideline_authority")
            result.reasons.append(
                f"Domain {domain!r} is a recognized guideline-issuing body and "
                f"the URL path OR title signals a clinical practice guideline / "
                f"consensus / scientific statement. High-authority secondary "
                f"evidence (T2 — guideline authority, NOT a primary study). "
                f"Canonical ACC/AHA guidelines are DOI articles with guideline "
                f"titles (no /guidelines/ path), so the title check is required. "
                f"Content stubs already returned T7 at Rule 1."
            )
            return result

    # ── Rule 8b (BUG-M-17, Codex pass 2): body-inspection override.
    # When live_retriever._detect_article_type_from_body found explicit
    # article-type metadata (meta tag / JSON-LD / Frontiers section
    # header / PRISMA marker / "we report a case" etc.) in the fetched
    # content, that secondary signal trumps the title-only heuristics.
    # Applied BEFORE R9/R10 so OpenAlex metadata can't upgrade a
    # body-detected case-report/perspective to T1.
    #
    # M-17f (Codex pass 7 structural pivot): gate the override by the
    # title-diagnostic check. If the title already carries explicit
    # article-type keywords ("systematic review", "case report",
    # "clinical practice guideline", etc.), R9/R10 already has enough
    # evidence to classify correctly, and body-signal false positives
    # must NOT demote primary papers. Body signal is logged as
    # advisory in this branch and does not change tier.
    body_signal = (signals.body_article_type or "").upper()
    if body_signal in ("SR_MA", "CASE_REPORT", "PERSPECTIVE", "GUIDELINE"):
        # M-17f: suppress override when title is article-type diagnostic
        title_has_article_type = _title_is_diagnostic_for_article_type(signals.title)
        # M-17g (Codex pass 8 CONDITIONAL): also suppress when title has
        # strong primary-study evidence AND OpenAlex confirms peer-
        # reviewed journal article. This prevents body-signal false
        # positives from demoting RCT titles such as "Randomized
        # placebo-controlled trial" or named-trial titles like
        # "SURPASS-9 trial".
        pub_type_for_gate = (signals.openalex_publication_type or "").lower()
        src_type_for_gate = (signals.openalex_source_type or "").lower()
        is_peer_reviewed_for_gate = (
            signals.openalex_is_peer_reviewed is True
            or src_type_for_gate == "journal"
        )
        title_is_primary_study = (
            _detect_primary_study_signal(signals.title)
            and is_peer_reviewed_for_gate
            and pub_type_for_gate in ("article", "review")
        )
        if title_has_article_type or title_is_primary_study:
            # Title already carries diagnostic evidence (article-type
            # keyword OR strong primary-study signal on a peer-reviewed
            # journal article). Log body as advisory and FALL THROUGH
            # to R9/R10 (do not return).
            gate_reason = (
                "article-type" if title_has_article_type else "primary-study"
            )
            result.reasons.append(
                f"R8b_body_signal_advisory_only: body={body_signal} "
                f"(title is diagnostic [{gate_reason}]; trusting R9/R10)"
            )
        else:
            # Title is NOT diagnostic — body signal is the primary
            # article-type evidence and wins over R9/R10.
            if body_signal == "SR_MA":
                result.tier = TierLevel.T2
                result.confidence = 0.85
                result.matched_rules.append("R8b_body_sr_ma")
                result.reasons.append(
                    "Body-inspection detected systematic review / meta-"
                    "analysis signal (meta tag, JSON-LD, PRISMA "
                    "reference, or abstract lead). T2 regardless of "
                    "title."
                )
            elif body_signal == "CASE_REPORT":
                result.tier = TierLevel.T4
                result.confidence = 0.8
                result.matched_rules.append("R8b_body_case_report")
                result.reasons.append(
                    "Body-inspection detected case-report signal. T4 "
                    "regardless of title."
                )
            elif body_signal == "GUIDELINE":
                result.tier = TierLevel.T4
                result.confidence = 0.8
                result.matched_rules.append("R8b_body_guideline")
                result.reasons.append(
                    "Body-inspection detected guideline / consensus / "
                    "practice-guide signal. T4 regardless of title."
                )
            else:  # PERSPECTIVE
                result.tier = TierLevel.T4
                result.confidence = 0.75
                result.matched_rules.append("R8b_body_perspective")
                result.reasons.append(
                    "Body-inspection detected perspective / commentary "
                    "/ editorial signal. T4 regardless of title."
                )
            return result

    # ── Rule 9: OpenAlex-indexed peer-reviewed journal article
    # Needs: publication_type in {article, review} AND source_type=journal
    pub_type = (signals.openalex_publication_type or "").lower()
    src_type = (signals.openalex_source_type or "").lower()
    is_peer_reviewed_hint = (
        signals.openalex_is_peer_reviewed is True
        or src_type == "journal"
    )
    if is_peer_reviewed_hint and pub_type in ("article", "review"):
        # Conference abstract check first (supplement paths, numbered abstracts)
        if _detect_conference_abstract(signals.title, signals.url):
            result.tier = TierLevel.T7
            result.confidence = 0.85
            result.matched_rules.append("R9_conference_abstract")
            result.reasons.append(
                f"OpenAlex: peer-reviewed journal {pub_type!r}, but title "
                f"or URL signals conference abstract / supplement issue. T7."
            )
            return result
        # Determine T1 / T2 / T4 from title heuristics + OpenAlex pub_type
        if _detect_systematic_review_from_title(signals.title):
            result.tier = TierLevel.T2
            result.confidence = 0.85
            result.matched_rules.append("R9_openalex_sr_or_ma")
            result.reasons.append(
                f"OpenAlex: peer-reviewed {pub_type!r} in journal; title "
                f"signals systematic review / meta-analysis. T2."
            )
        elif _detect_narrative_flavor_from_title(signals.title):
            result.tier = TierLevel.T4
            result.confidence = 0.8
            result.matched_rules.append("R9_openalex_narrative_review")
            result.reasons.append(
                f"OpenAlex: peer-reviewed {pub_type!r} in journal; title "
                f"signals narrative review / commentary / perspective / "
                f"update. T4."
            )
        elif pub_type == "review":
            # OpenAlex explicitly marks this as a "review" but the title
            # didn't trip the SR/MA or narrative-flavor detectors. Default
            # to T4 narrative review — OpenAlex's type field is informative
            # even when the title is a bare drug-plus-condition phrasing.
            # If it were actually a systematic review, the title would
            # contain the SR/MA marker (PRISMA requires it).
            result.tier = TierLevel.T4
            result.confidence = 0.7
            result.matched_rules.append("R9_openalex_pubtype_review")
            result.reasons.append(
                f"OpenAlex: publication_type == 'review' but title does "
                f"not signal systematic review. Defaulting to T4 narrative "
                f"review; manual review recommended if this paper is "
                f"actually a network-meta-analysis or scoping review with "
                f"a non-standard title."
            )
        elif _detect_guideline_or_explainer_title(signals.title):
            # BUG-M-10 (Codex pass 10): OpenAlex sometimes returns
            # clinical-practice guidelines or policy-explainer content
            # (e.g., PMC-hosted "2025 Guidelines for direct oral
            # anticoagulants" or "Predetermined Change Control Plans:
            # Guiding Principles") as pub_type=article. That metadata
            # is syntactically an article but the content is practice
            # guidance or policy analysis, not primary research. Route
            # to T4 narrative / analytical content.
            result.tier = TierLevel.T4
            result.confidence = 0.8
            result.matched_rules.append("R9_openalex_guideline_explainer")
            result.reasons.append(
                f"OpenAlex: peer-reviewed {pub_type!r} in journal, but "
                f"title signals guideline / guiding principles / "
                f"explainer / policy brief. Practice guidance or policy "
                f"analysis, not primary research. T4."
            )
        else:
            # BUG-M-11 (Codex pass 11): require the domain to be on a
            # known peer-reviewed-journal allowlist (or NIH literature
            # aggregator) before granting T1. OpenAlex alone is not
            # enough: it sometimes returns article+journal metadata
            # for trade-association whitepapers, industry insights,
            # web explainers, and trade news (Codex named 7 such
            # hallucinations in cycle 3). Domains outside the
            # allowlist route to T4 narrative instead.
            if not (_domain_matches(domain, PEER_REVIEWED_JOURNAL_DOMAINS)
                    or _domain_matches(domain, NIH_LITERATURE_HOSTS)
                    or _has_peer_reviewed_doi_prefix(signals.url)
                    or _is_doi_org_journal_with_venue(signals)):
                result.tier = TierLevel.T4
                result.confidence = 0.65
                result.matched_rules.append(
                    "R9_openalex_unverified_host_demoted_to_t4"
                )
                result.reasons.append(
                    f"OpenAlex said peer-reviewed {pub_type!r} in journal, "
                    f"but domain {domain!r} is NOT on the known "
                    f"peer-reviewed-journal allowlist "
                    f"(PEER_REVIEWED_JOURNAL_DOMAINS or NIH_LITERATURE_HOSTS "
                    f"or PEER_REVIEWED_DOI_PREFIXES) and is not a doi.org-hosted "
                    f"canonical DOI with a resolved OpenAlex journal venue. "
                    f"Routing to T4 to avoid overclassifying industry / "
                    f"trade / web content as primary research. Add the "
                    f"domain to the allowlist if it is genuinely a "
                    f"peer-reviewed journal."
                )
                return result
            # BUG-M-12 (Codex pass 12): the primary-signal requirement
            # was too strict — bare NEJM/Lancet/JAMA papers with
            # titles like "Tirzepatide in type 2 diabetes" or
            # "Semaglutide in Obesity" are legitimate primary trials
            # but lack positive RCT/phase markers in the title. Rely
            # instead on (i) OpenAlex full-title enrichment in
            # live_retriever (so SR/MA suffixes aren't truncated) and
            # (ii) expanded narrative markers ("perspective for",
            # "for clinicians") to catch guidance articles.
            # I-bug-771 (#812, Codex reconcile B): low-quality OA (MDPI)
            # primary articles do NOT earn T1. The SR/MA branch above
            # already routed genuine MDPI systematic reviews to T2, so this
            # only catches the primary path (the demonstrated afib over-credit
            # was MDPI-primary -> T1). Demote to T4.
            if _is_low_quality_oa(domain, signals.url):
                result.tier = TierLevel.T4
                result.confidence = 0.7
                result.matched_rules.append("R9_low_quality_oa_primary_demoted")
                result.reasons.append(
                    f"OpenAlex: peer-reviewed {pub_type!r} in journal, but "
                    f"domain {domain!r} (or DOI prefix) is a low-quality / "
                    f"high-volume OA publisher. Primary articles do not earn "
                    f"T1 (variable methodological quality); T4 ceiling. A "
                    f"genuine full-title systematic review / meta-analysis "
                    f"would have routed to T2 in the earlier branch."
                )
                return result
            result.tier = TierLevel.T1
            result.confidence = 0.8
            result.matched_rules.append("R9_openalex_primary_study")
            result.reasons.append(
                f"OpenAlex: peer-reviewed {pub_type!r} in journal; "
                f"title does not signal review. Classified as T1 primary "
                f"study. (A stronger classifier would inspect study-design "
                f"keywords in the title / abstract.)"
            )
        return result

    # ── Rule 10: Peer-reviewed-journal-domain heuristic when no OpenAlex data.
    # Also fires for NIH_LITERATURE_HOSTS (PMC, PubMed) which are peer-
    # reviewed literature aggregators, NOT regulatory.
    is_nih_lit = _domain_matches(domain, NIH_LITERATURE_HOSTS)
    if _domain_matches(domain, PEER_REVIEWED_JOURNAL_DOMAINS) or is_nih_lit:
        # Conference abstract check BEFORE anything else — '1745-P:' and
        # similar prefixes are T7 regardless of journal prestige.
        if _detect_conference_abstract(signals.title, signals.url):
            result.tier = TierLevel.T7
            result.confidence = 0.85
            result.matched_rules.append("R10_conference_abstract")
            result.reasons.append(
                f"Domain {domain!r} is a peer-reviewed journal but title "
                f"or URL signals conference abstract / poster / supplement "
                f"issue. T7."
            )
            return result
        if _detect_systematic_review_from_title(signals.title):
            result.tier = TierLevel.T2
            result.confidence = 0.75
            result.matched_rules.append("R10_journal_domain_sr_title")
            result.reasons.append(
                f"Domain {domain!r} is a peer-reviewed journal; title "
                f"signals SR / MA. T2."
            )
            return result
        if _detect_narrative_flavor_from_title(signals.title):
            result.tier = TierLevel.T4
            result.confidence = 0.7
            result.matched_rules.append("R10_journal_domain_narrative")
            result.reasons.append(
                f"Domain {domain!r} is a peer-reviewed journal; title "
                f"signals narrative review / commentary / perspective. T4."
            )
            return result
        # BUG-M-14 revert + BUG-M-15 (Codex pass 15 CONDITIONAL):
        # Blanket primary-signal requirement was too strict (cycle 7 =
        # 0 releases). Instead, apply narrow targeted guards for the
        # specific false-T1 patterns Codex pass 15 named.

        # M-15 guard 1: truncated title (ends with "..." or is very
        # short). Serper snippets are often cut mid-title. Without a
        # full title, R10 can't distinguish primary from SR/MA /
        # perspective / guideline — demote to T4.
        _title_stripped = (signals.title or "").strip()
        if _title_stripped.endswith("...") or _title_stripped.endswith("…"):
            result.tier = TierLevel.T4
            result.confidence = 0.55
            result.matched_rules.append("R10_journal_domain_truncated_title_demoted")
            result.reasons.append(
                f"Domain {domain!r} is a peer-reviewed journal but the "
                f"title appears truncated (ends with ellipsis). Can't "
                f"reliably detect SR/MA/perspective/guideline from a "
                f"partial title, so defaulting to T4. Fetch the full "
                f"title via OpenAlex display_name or page content to "
                f"reclassify."
            )
            return result

        # M-15 guard 2 REVERTED: the blanket "NIH aggregator → T4 when
        # no OpenAlex metadata" demoted too many legitimate PMC/PubMed
        # primaries (cycle 9: 0 releases / 8 aborts, T1=0% everywhere).
        # OpenAlex lookups fail often enough that the fallback path
        # hits NIH content regularly. Keeping truncated-title guard
        # (guard 1) and society-tool guard (guard 3) which are more
        # surgical. Codex pass 16 can assess whether remaining NIH
        # hallucinations need a narrower fix.

        # M-15 guard 3: professional-society tool / dosing / practice-
        # support PDFs on acc.org, ahajournals.org, etc. These pages
        # ship clinical decision-support tools, not research reports.
        _url_lower = (signals.url or "").lower()
        _society_tool_markers = (
            "/tools/", "/tool/",
            "/practice-support/", "/practice-resources/",
            "/information-graphics/", "/infographic",
            "/dosing/", "-dosing-",
            "/clinical-tools/",
        )
        if domain.endswith("acc.org") and any(
            m in _url_lower for m in _society_tool_markers
        ):
            result.tier = TierLevel.T3
            result.confidence = 0.85
            result.matched_rules.append("R10_society_tool_demoted")
            result.reasons.append(
                f"URL path on {domain!r} matches professional-society "
                f"tool / practice-support / dosing / infographic pattern. "
                f"Clinical decision-support reference, not primary "
                f"research. T3 (professional-society guidance)."
            )
            return result

        # I-bug-771 (#812, Codex reconcile B): low-quality OA (MDPI) primary
        # articles do NOT earn presumed-T1 here either (the SR/MA-title branch
        # above already routed genuine reviews to T2). Demote to T4.
        if _is_low_quality_oa(domain, signals.url):
            result.tier = TierLevel.T4
            result.confidence = 0.6
            result.matched_rules.append("R10_low_quality_oa_primary_demoted")
            result.reasons.append(
                f"Domain {domain!r} (or DOI prefix) is a low-quality / "
                f"high-volume OA publisher; presumed-primary articles do not "
                f"earn T1. T4 ceiling. A genuine SR/MA title would have routed "
                f"to T2 above."
            )
            return result
        # Journal domain without OpenAlex, not NIH aggregator, not
        # society-tool URL pattern, title not truncated, and no
        # SR/MA/narrative/guideline signals fired in earlier branches:
        # default T1 presumed-primary.
        result.tier = TierLevel.T1
        result.confidence = 0.6
        result.matched_rules.append("R10_journal_domain_presumed_primary")
        result.reasons.append(
            f"Domain {domain!r} is a peer-reviewed journal "
            f"and title does not signal review or abstract. "
            f"Presumed T1 primary (low confidence — consider manual review)."
        )
        return result

    # ── Rule 11 fallthrough: OpenAlex preprint/book-chapter/dataset
    if pub_type == "preprint" or src_type == "repository":
        result.tier = TierLevel.T4
        result.confidence = 0.7
        result.matched_rules.append("R11_openalex_preprint_or_repo")
        result.reasons.append(
            f"OpenAlex: {pub_type!r} / {src_type!r} — preprint or "
            f"repository; not peer-reviewed. T4."
        )
        return result
    if pub_type in ("book-chapter", "book", "dataset", "editorial", "letter"):
        result.tier = TierLevel.T4
        result.confidence = 0.65
        result.matched_rules.append(f"R11_openalex_{pub_type}")
        result.reasons.append(
            f"OpenAlex: {pub_type!r}. T4 narrative/unreviewed."
        )
        return result

    # ── No rule matched: honest UNKNOWN
    result.tier = TierLevel.UNKNOWN
    result.confidence = 0.0
    result.matched_rules.append("no_rule_matched")
    result.reasons.append(
        "No classifier rule matched. Marking UNKNOWN (not BRONZE / T6) so "
        "misconfiguration surfaces. Typical fixes: add the domain to "
        "REGULATORY_DOMAINS / NEWS_BLOG_DOMAINS / PEER_REVIEWED_JOURNAL_DOMAINS; "
        "supply a source_type_hint upstream; provide OpenAlex metadata."
    )
    return result


# Convenience one-shot helpers for simpler call sites.
def classify_url(url: str, content_length: int = 0, **extra: Any) -> ClassificationResult:
    """Classify a source by URL + content length + optional extras."""
    signals = ClassificationSignals(
        url=url,
        fetched_content_length=content_length,
        **extra,
    )
    return classify_source_tier(signals)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 0a (GH #983): the authority-model ON path (shadow behind the kill-switch)
# ─────────────────────────────────────────────────────────────────────────────

# authority_confidence -> a representative numeric confidence for the legacy
# `confidence` field (so existing consumers that read `.confidence` still get a
# float). These are VIEW knobs, not host knowledge.
_AUTHORITY_CONFIDENCE_TO_FLOAT = {
    "HIGH": 0.9,
    "MEDIUM": 0.7,
    "LOW": 0.5,
}


def _classify_via_authority_model(
    signals: ClassificationSignals,
) -> ClassificationResult:
    """ON path: compute authority + render the clinical T1-T7 VIEW.

    Returns a ClassificationResult with the five legacy fields populated off the
    rendered view PLUS the four additive authority fields and
    signals_used["authority"] (additive; no consumer reads it in 0a — shadow).
    """
    # Lazy import keeps the OFF path free of the authority package + its YAML
    # loader, and avoids any import-time coupling.
    from dataclasses import asdict

    from src.polaris_graph.authority import (
        ClinicalViewInput,
        render_clinical_tier,
        score_source_authority,
    )

    authority_result = score_source_authority(signals)
    tier_str = render_clinical_tier(
        ClinicalViewInput(
            publication_type=signals.openalex_publication_type,
            source_type=signals.openalex_source_type,
            is_retracted=signals.openalex_is_retracted,
            fetched_content_length=signals.fetched_content_length,
            title=signals.title,
            authority=authority_result,
        )
    )
    tier = TierLevel(tier_str)
    confidence = _AUTHORITY_CONFIDENCE_TO_FLOAT.get(
        authority_result.authority_confidence.value, 0.5
    )

    result = ClassificationResult(
        tier=tier,
        confidence=confidence,
        reasons=list(authority_result.reasons),
        matched_rules=["authority_model"],
        signals_used={
            "domain": _normalize_domain(signals.url),
            "authority": asdict(authority_result),
        },
        authority_score=authority_result.authority_score,
        source_class=authority_result.source_class.value,
        corroboration_count=authority_result.corroboration_count,
        authority_confidence=authority_result.authority_confidence.value,
    )
    return result
