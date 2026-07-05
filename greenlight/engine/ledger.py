"""Compliance ledger — one row per marketing claim under review."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ClaimCheck:
    claim_id: str
    sku: str
    text: str
    claim_type: str
    status: str = "pending"  # pending | checking | substantiated | needs-evidence | blocked
    regulation: Optional[str] = None
    citation: Optional[str] = None
    evidence: Optional[str] = None
    remediation: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OpportunityRecommendation:
    opportunity_id: str
    sku: str
    text: str
    claim_type: str
    status: str = "pending"  # pending | substantiated | needs-evidence | rejected
    trend_keyword: Optional[str] = None
    demand_index: Optional[float] = None
    uplift_pct: Optional[float] = None
    citation: Optional[str] = None
    regulation: Optional[str] = None
    remediation: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComplianceLedger:
    brand: str
    season: str
    turnover_eur: float
    claims: List[ClaimCheck] = field(default_factory=list)
    opportunities: List[OpportunityRecommendation] = field(default_factory=list)
    commercial: Dict[str, Any] = field(default_factory=dict)
    determination: Optional[Dict[str, Any]] = None

    @property
    def blocked(self):
        return [c for c in self.claims if c.status == "blocked"]

    @property
    def cleared(self):
        return [c for c in self.claims if c.status == "substantiated"]

    @property
    def recommended_opportunities(self):
        return [o for o in self.opportunities if o.status == "substantiated"]

    @property
    def confidence(self):
        if not self.claims:
            return 0.0
        ok = sum(1 for c in self.claims if c.status == "substantiated")
        return round(ok / len(self.claims), 2)
