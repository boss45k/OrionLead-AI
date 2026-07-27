"""
Entity Graph
============
Lightweight in-memory directed graph for entity identity resolution.

Node types
----------
  COMPANY   — legal or trading company name
  PERSON    — full personal name
  EMAIL     — email address (normalized lower-case)
  DOMAIN    — apex domain (e.g. "acme.io")
  LINKEDIN  — linkedin.com/in/<slug> or linkedin.com/company/<slug>
  TECH      — detected technology name

Edge types
----------
  works_at        PERSON    → COMPANY
  has_email       PERSON    → EMAIL
  has_domain      COMPANY   → DOMAIN
  email_on_domain EMAIL     → DOMAIN
  linkedin_for    PERSON    → LINKEDIN   |  COMPANY → LINKEDIN
  uses_tech       COMPANY   → TECH

Each edge carries a confidence weight (0.0-1.0) based on the reliability
of the source that produced it.

The graph is a session-level singleton — it accumulates data across a
collection run and is cleared between runs via reset().

Thread safety
-------------
All mutation operations acquire a reentrant lock.
Read operations (score_lead, get_connections) do NOT lock — they take
a momentary snapshot which is safe under Python's GIL.
"""

from __future__ import annotations

import logging
import re
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, DefaultDict, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ── Node / Edge types ─────────────────────────────────────────────────────────

class NodeType(str, Enum):
    COMPANY  = "company"
    PERSON   = "person"
    EMAIL    = "email"
    DOMAIN   = "domain"
    LINKEDIN = "linkedin"
    TECH     = "tech"


class EdgeType(str, Enum):
    WORKS_AT        = "works_at"
    HAS_EMAIL       = "has_email"
    HAS_DOMAIN      = "has_domain"
    EMAIL_ON_DOMAIN = "email_on_domain"
    LINKEDIN_FOR    = "linkedin_for"
    USES_TECH       = "uses_tech"
    SAME_COMPANY    = "same_company"     # resolved alias / variant


@dataclass
class Node:
    id:   str        # canonical identifier (normalized)
    type: NodeType
    aliases: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Edge:
    src:    str          # node id
    dst:    str          # node id
    type:   EdgeType
    weight: float = 1.0  # confidence (0-1)
    source: str   = ""   # data source that produced this edge


# ── Source reliability weights ────────────────────────────────────────────────
# Higher = more trustworthy source for establishing edges.

_SOURCE_WEIGHTS: Dict[str, float] = {
    "apollo":    0.95,
    "hunter":    0.90,
    "pdl":       0.88,
    "clearbit":  0.85,
    "crunchbase":0.80,
    "linkedin":  0.80,
    "github":    0.70,
    "web":       0.60,
    "public_web":0.60,
    "news":      0.50,
    "reddit":    0.35,
    "twitter":   0.35,
    "unknown":   0.30,
}


class EntityGraph:
    """
    In-memory entity graph with adjacency lists.

    Nodes and edges are keyed by canonical node IDs.
    The adjacency dict maps src_id → list of outgoing edges.
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, Node] = {}
        self._adj:   DefaultDict[str, List[Edge]] = defaultdict(list)
        self._lock   = threading.RLock()
        self._lead_count = 0

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_lead(self, lead: Dict[str, Any], source: str = "unknown") -> None:
        """
        Ingest one lead dict into the graph.
        Extracts all entities and adds edges between them.
        """
        weight = _SOURCE_WEIGHTS.get(source.lower(), 0.3)

        company  = self._normalize(lead.get("company") or "", NodeType.COMPANY)
        name     = self._normalize(lead.get("name") or "", NodeType.PERSON)
        email    = self._normalize_email(lead.get("email") or "")
        domain   = self._extract_domain(lead.get("website") or "", email)
        linkedin = self._normalize_linkedin(lead.get("linkedin_url") or "")
        techs    = lead.get("data_points", {}).get("tech_stack", []) or []

        with self._lock:
            # Register nodes
            if company:  self._upsert_node(company, NodeType.COMPANY, lead.get("company", ""))
            if name:     self._upsert_node(name, NodeType.PERSON, lead.get("name", ""))
            if email:    self._upsert_node(email, NodeType.EMAIL,  lead.get("email", ""))
            if domain:   self._upsert_node(domain, NodeType.DOMAIN, domain)
            if linkedin: self._upsert_node(linkedin, NodeType.LINKEDIN, lead.get("linkedin_url", ""))
            for t in techs:
                tk = self._normalize(t, NodeType.TECH)
                if tk: self._upsert_node(tk, NodeType.TECH, t)

            # Add edges
            if name and company:
                self._add_edge(name, company, EdgeType.WORKS_AT, weight, source)
            if name and email:
                self._add_edge(name, email, EdgeType.HAS_EMAIL, weight, source)
            if company and domain:
                self._add_edge(company, domain, EdgeType.HAS_DOMAIN, weight, source)
            if email and domain:
                self._add_edge(email, domain, EdgeType.EMAIL_ON_DOMAIN, weight, source)
            if name and linkedin:
                self._add_edge(name, linkedin, EdgeType.LINKEDIN_FOR, weight, source)
            if company and linkedin and "company" in linkedin:
                self._add_edge(company, linkedin, EdgeType.LINKEDIN_FOR, weight, source)
            for t in techs:
                tk = self._normalize(t, NodeType.TECH)
                if tk and company:
                    self._add_edge(company, tk, EdgeType.USES_TECH, weight * 0.8, source)

        self._lead_count += 1

    def reset(self) -> None:
        """Clear all graph state (call between collection runs)."""
        with self._lock:
            self._nodes.clear()
            self._adj.clear()
            self._lead_count = 0
        logger.debug("[graph] entity graph reset")

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def score_lead(self, lead: Dict[str, Any]) -> float:
        """
        Returns a graph confidence score (0.0-1.0) for a lead based on
        how many corroborating entities and connections exist in the graph.
        """
        company  = self._normalize(lead.get("company") or "", NodeType.COMPANY)
        email    = self._normalize_email(lead.get("email") or "")
        domain   = self._extract_domain(lead.get("website") or "", email)
        linkedin = self._normalize_linkedin(lead.get("linkedin_url") or "")

        score = 0.0
        max_score = 0.0

        # Company known + has edges?
        max_score += 30.0
        if company and company in self._nodes:
            score += 15.0
            edges = self._adj.get(company, [])
            if edges:
                score += min(15.0, len(edges) * 3.0)

        # Email known?
        max_score += 25.0
        if email and email in self._nodes:
            score += 20.0
            # Email on expected domain?
            if domain and email.endswith(f"@{domain}"):
                score += 5.0

        # Domain known?
        max_score += 20.0
        if domain and domain in self._nodes:
            score += 15.0
            edges = self._adj.get(domain, [])
            # Multiple people from same domain = strong company signal
            score += min(5.0, len(edges) * 1.0)

        # LinkedIn verified?
        max_score += 15.0
        if linkedin and linkedin in self._nodes:
            score += 15.0

        # Cross-corroboration: email domain matches company domain
        max_score += 10.0
        if email and domain and email.endswith(f"@{domain}"):
            score += 10.0

        if max_score == 0:
            return 0.0
        return min(1.0, score / max_score)

    def get_company_contacts(self, domain: str) -> List[str]:
        """Return all known email addresses for a domain."""
        out: List[str] = []
        for node_id, node in self._nodes.items():
            if node.type == NodeType.EMAIL and node_id.endswith(f"@{domain}"):
                out.append(node.metadata.get("original", node_id))
        return out

    def get_stats(self) -> Dict[str, int]:
        counts: Dict[str, int] = defaultdict(int)
        for node in self._nodes.values():
            counts[node.type.value] += 1
        edge_count = sum(len(edges) for edges in self._adj.values())
        counts["edges"] = edge_count
        counts["leads_ingested"] = self._lead_count
        return dict(counts)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _upsert_node(self, node_id: str, ntype: NodeType, original: str) -> Node:
        if node_id not in self._nodes:
            self._nodes[node_id] = Node(id=node_id, type=ntype, metadata={"original": original})
        else:
            if original:
                self._nodes[node_id].aliases.add(original)
        return self._nodes[node_id]

    def _add_edge(
        self,
        src: str,
        dst: str,
        etype: EdgeType,
        weight: float,
        source: str,
    ) -> None:
        # Avoid exact duplicate edges (same src→dst→type from same source)
        existing = self._adj[src]
        for e in existing:
            if e.dst == dst and e.type == etype and e.source == source:
                # Update weight if stronger
                if weight > e.weight:
                    e.weight = weight
                return
        self._adj[src].append(Edge(src=src, dst=dst, type=etype, weight=weight, source=source))

    @staticmethod
    def _normalize(value: str, ntype: NodeType) -> str:
        v = value.strip().lower()
        # Remove punctuation for company / person keys
        if ntype in (NodeType.COMPANY, NodeType.PERSON):
            v = re.sub(r"[^\w\s]", "", v)
            v = re.sub(r"\s+", "_", v)
        return v if len(v) >= 2 else ""

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def _normalize_linkedin(url: str) -> str:
        url = url.strip().lower()
        if not url:
            return ""
        try:
            p = urlparse(url if url.startswith("http") else f"https://{url}")
            path = p.path.rstrip("/")
            if "/in/" in path or "/company/" in path:
                return path
        except Exception:
            pass
        return url

    @staticmethod
    def _extract_domain(website: str, email: str) -> str:
        if website:
            try:
                h = urlparse(website).netloc.lower().replace("www.", "")
                if h:
                    return h
            except Exception:
                pass
        if "@" in email:
            return email.split("@")[1].lower()
        return ""


# ── Singleton ─────────────────────────────────────────────────────────────────

_graph: Optional[EntityGraph] = None


def get_entity_graph() -> EntityGraph:
    global _graph
    if _graph is None:
        _graph = EntityGraph()
        logger.info("[graph] EntityGraph initialized")
    return _graph
