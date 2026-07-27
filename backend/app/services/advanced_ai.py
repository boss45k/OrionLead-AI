"""
ML Stack — local models for scoring, deduplication, and NLP
=============================================================
This module is the ML/local-model layer. It is NOT a duplicate of the main
AI path (gemini_service.py) — it serves a different purpose: offline scoring,
vector dedup, and NLP feature extraction.

Components managed here (all thread-safe singletons):
  1. Ollama / Mistral 7B  — local LLM for embedding + NLP (no API key needed)
  2. spaCy                — named-entity recognition for lead field extraction
  3. XGBoost ML model     — 35-feature lead scoring (see ml_model.py)
  4. FAISS index          — vector-similarity deduplication
  5. sentence-transformers — text embeddings for FAISS

AI provider map for this project:
  /api/v1/ai/*   → services/gemini_service.AIService  (Gemini → Groq → rules)
  /api/v1/agents/* → agents/query_agent → llm/integration.LLMIntegration (OpenAI)
  ML scoring     → THIS FILE + services/ml_model.XGBLeadScoringModel

NOTE: Thread-safe singleton initialization — all getters use double-checked
locking so concurrent Flask workers share a single instance per process.

Re-exports get_ml_model / extract_features so ml_decision_layer.py can import
from one place:
    from app.services.advanced_ai import get_ml_model, extract_features
"""

import logging
import json
import numpy as np
from typing import Dict, Any, Optional, List
import pickle
from pathlib import Path
import threading

# ── ML layer (XGBoost, 30 features, SHAP) ─────────────────────────────────────
# ml_model.py owns the model class and feature extractor.
# Re-exporting extract_features here keeps ml_decision_layer.py's import working:
#     from app.services.advanced_ai import get_ml_model, extract_features
from app.services.ml_model import XGBLeadScoringModel, extract_features  # noqa: F401

logger = logging.getLogger(__name__)

# Thread-safe locks for initialization
_init_lock = threading.Lock()
_initialized = False

# Singleton instances (protected by lock)
_ollama_client = None
_spacy_nlp = None
_ml_model = None
_faiss_dedup = None
_embedder = None

# ============================================================================
# 1. OLLAMA - LLM Engine (Core AI)
# ============================================================================

def initialize_ollama():
    """Initialize Ollama client"""
    logger.debug("initialize_ollama() called")
    try:
        import ollama
        logger.debug("ollama module imported successfully")
        return ollama
    except ImportError as e:
        logger.warning(f"Ollama not available ({e}). Install with: pip install ollama")
        logger.info("Also install Ollama runtime from: https://ollama.ai")
        return None
    except Exception as e:
        logger.error(f"Ollama initialization error: {e}")
        return None


def qualify_with_ollama(lead_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Qualify lead using Ollama + Mistral 7B"""
    try:
        import ollama
        
        # Prepare lead info
        interests = lead_data.get('interests', [])
        if not isinstance(interests, list):
            interests = [interests] if interests else []
        interests_str = ', '.join(str(i) for i in interests) if interests else 'None'
        
        prompt = f"""You are a sales qualification expert. Analyze this lead and provide a JSON response.

Lead Details:
- Name: {lead_data.get('name', 'Unknown')}
- Company: {lead_data.get('company', 'Unknown')}
- Position: {lead_data.get('position', 'Unknown')}
- Email: {lead_data.get('email', 'Unknown')}
- Interests: {interests_str}
- Source: {lead_data.get('source', 'Unknown')}

Score this lead 0-100 based on fit. Respond with ONLY this JSON format (no markdown):
{{"score": <number>, "category": "Hot|Warm|Cold", "reason": "<brief explanation>"}}"""
        
        # Call Ollama with proper error handling
        response = ollama.generate(
            model="mistral",
            prompt=prompt,
            stream=False
        )
        
        # Parse response
        response_text = response.get('response', '{}').strip()
        # Remove markdown code blocks if present
        if response_text.startswith('```'):
            response_text = response_text.split('```')[1]
            if response_text.startswith('json'):
                response_text = response_text[4:]
        response_text = response_text.strip()
        
        result = json.loads(response_text)
        
        ollama_result = {
            'score': min(max(int(result.get('score', 50)), 0), 100),
            'category': result.get('category', 'Warm'),
            'confidence': 0.85,
            'reason': result.get('reason', 'Ollama evaluation'),
            'ai_provider': 'Ollama (Mistral 7B)',
            'model': 'mistral'
        }
        logger.debug(f"Ollama qualification successful: {lead_data.get('name', 'Unknown')} → Score: {ollama_result['score']}")
        return ollama_result
    except ImportError as e:
        logger.warning(f"Ollama module not available: {str(e)}")
        logger.info("Install with: pip install ollama")
        return None
    except ConnectionError as e:
        logger.warning(f"Ollama connection error: {str(e)}")
        logger.info("Make sure Ollama is running: ollama serve")
        return None
    except Exception as e:
        logger.error(f"Ollama qualification error: {str(e)}")
        return None


# ============================================================================
# 2. spaCY - NLP Processing Layer
# ============================================================================

def initialize_spacy():
    """Initialize spaCy NLP model"""
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
        return nlp
    except Exception as e:
        logger.error(f"spaCy initialization error: {str(e)}")
        return None


def extract_entities(text: str, nlp) -> Dict[str, List[str]]:
    """Extract entities from text using spaCy"""
    if not nlp or not text:
        return {'persons': [], 'organizations': [], 'emails': [], 'phones': []}
    
    try:
        doc = nlp(text)
        entities = {
            'persons': [],
            'organizations': [],
            'emails': [],
            'phones': []
        }
        
        # Extract named entities
        for ent in doc.ents:
            if ent.label_ == 'PERSON':
                entities['persons'].append(ent.text)
            elif ent.label_ == 'ORG':
                entities['organizations'].append(ent.text)
        
        # Simple email extraction
        import re
        emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)
        entities['emails'] = list(set(emails))
        
        # Simple phone extraction
        phones = re.findall(r'\+?1?\d{9,15}', text)
        entities['phones'] = list(set(phones))
        
        return entities
    except Exception as e:
        logger.error(f"Entity extraction error: {str(e)}")
        return {'persons': [], 'organizations': [], 'emails': [], 'phones': []}


def clean_text(text: str, nlp) -> str:
    """Clean and normalize text using spaCy"""
    if not nlp or not text:
        return ""
    
    try:
        doc = nlp(text.lower())
        # Remove stopwords and keep meaningful tokens
        tokens = [token.lemma_ for token in doc if not token.is_stop and token.is_alpha]
        return ' '.join(tokens)
    except Exception as e:
        logger.error(f"Text cleaning error: {str(e)}")
        return text.lower()



# ============================================================================
# 3. ML Classification Layer
#    Implemented in ml_model.py — XGBoost, 30 features, Optuna, SHAP.
#    XGBLeadScoringModel and extract_features are imported at the top.
# ============================================================================


# ============================================================================
# 4. FAISS - Vector Search & Deduplication
# ============================================================================

class FAISSDeduplicator:
    """Lead deduplication using FAISS vector search"""
    
    def __init__(self):
        self.index = None
        self.embeddings = None
        self.lead_ids = []
        self.embedding_dim = 384  # sentence-transformers default
        self.index_path = Path(__file__).parent.parent.parent / 'models' / 'faiss_index.bin'
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
    
    def initialize_index(self):
        """Initialize FAISS index"""
        try:
            import faiss
            self.index = faiss.IndexFlatL2(self.embedding_dim)
            logger.info("FAISS index initialized")
        except Exception as e:
            logger.error(f"FAISS initialization error: {str(e)}")
    
    def add_lead(self, lead_id: str, embedding: np.ndarray) -> None:
        """Add lead embedding to FAISS index"""
        try:
            if self.index is None:
                self.initialize_index()
            
            if self.index is not None and embedding.shape[0] == 1:
                self.index.add(embedding.astype(np.float32))  # type: ignore
                self.lead_ids.append(lead_id)
        except Exception as e:
            logger.error(f"Error adding lead to FAISS: {str(e)}")
    
    def find_duplicates(self, embedding: np.ndarray, threshold: float = 0.85) -> List[str]:
        """
        Find potential duplicate leads using cosine similarity.

        all-MiniLM-L6-v2 produces L2-normalised embeddings, so:
            cosine_similarity = 1 - l2_distance² / 2
        Threshold 0.85 means texts must be ≥85% similar to count as duplicates.
        """
        try:
            if self.index is None or self.index.ntotal == 0:
                return []

            k = min(5, self.index.ntotal)
            distances, indices = self.index.search(embedding.astype(np.float32), k)  # type: ignore

            similar = []
            for idx, l2_dist in zip(indices[0], distances[0]):
                # Convert L2 distance to cosine similarity for normalised vectors
                cosine_sim = max(0.0, 1.0 - float(l2_dist) ** 2 / 2.0)
                if cosine_sim >= threshold and int(idx) < len(self.lead_ids):
                    similar.append(self.lead_ids[int(idx)])

            return similar
        except Exception as e:
            logger.error(f"FAISS search error: {str(e)}")
            return []
    
    def save_index(self):
        """Persist FAISS index"""
        try:
            import faiss
            if self.index is not None:
                faiss.write_index(self.index, str(self.index_path))
                with open(self.index_path.with_suffix('.meta'), 'wb') as f:
                    pickle.dump(self.lead_ids, f)
        except Exception as e:
            logger.error(f"Error saving FAISS index: {str(e)}")
    
    def load_index(self):
        """Load persisted FAISS index"""
        try:
            import faiss
            if self.index_path.exists():
                self.index = faiss.read_index(str(self.index_path))
                with open(self.index_path.with_suffix('.meta'), 'rb') as f:
                    self.lead_ids = pickle.load(f)
                logger.info(f"Loaded FAISS index with {self.index.ntotal} leads")
        except Exception as e:
            logger.error(f"Error loading FAISS index: {str(e)}")


# ============================================================================
# 5. SENTENCE-TRANSFORMERS - Embeddings
# ============================================================================

def initialize_embedder():
    """Initialize sentence-transformers embedding model (local cache only)."""
    try:
        import os as _os
        import logging as _logging
        for _noisy in ('sentence_transformers', 'transformers', 'transformers.modeling_utils'):
            _logging.getLogger(_noisy).setLevel(_logging.WARNING)

        # Force offline mode — never attempt HuggingFace network calls.
        # The model must already be in the local cache; if it isn't, skip quietly.
        _os.environ.setdefault('HF_HUB_OFFLINE', '1')
        _os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')

        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer('all-MiniLM-L6-v2', local_files_only=True)
        logger.info("Sentence-Transformers model loaded from local cache")
        return model
    except Exception as e:
        logger.warning(f"Embedder not available (model not cached locally): {str(e)[:80]}")
        return None


def generate_lead_embedding(lead_data: Dict[str, Any], embedder) -> Optional[np.ndarray]:
    """Generate vector embedding for a lead"""
    if not embedder:
        return None
    
    try:
        # Combine lead information into text
        text_parts = [
            lead_data.get('name', ''),
            lead_data.get('company', ''),
            lead_data.get('position', ''),
            ' '.join(str(i) for i in lead_data.get('interests', [])) if lead_data.get('interests') else ''
        ]
        text = ' '.join(filter(None, text_parts))
        
        if not text:
            return None
        
        embedding = embedder.encode([text], convert_to_numpy=True, show_progress_bar=False)
        return embedding.astype(np.float32)
    except Exception as e:
        logger.error(f"Embedding generation error: {str(e)}")
        return None


# ============================================================================
# MAIN - Advanced AI Qualification
# ============================================================================


def get_ollama_client():
    """Get Ollama client (ensures initialization)"""
    global _ollama_client, _initialized
    if not _initialized:
        initialize_advanced_ai()
    return _ollama_client


def get_spacy_nlp():
    """Get spaCy NLP model (ensures initialization)"""
    global _spacy_nlp, _initialized
    if not _initialized:
        initialize_advanced_ai()
    return _spacy_nlp


def get_ml_model():
    """Get ML model (ensures initialization)"""
    global _ml_model, _initialized
    if not _initialized:
        initialize_advanced_ai()
    return _ml_model


def is_ml_model_ready() -> bool:
    """
    Fast check — returns True only if a trained model is in memory.
    Does NOT trigger initialization; avoids the slow first-load overhead
    when called from the 5-second ML timeout thread.
    """
    return _initialized and _ml_model is not None and _ml_model.is_ready()


def get_faiss_dedup():
    """Get FAISS deduplication (ensures initialization)"""
    global _faiss_dedup, _initialized
    if not _initialized:
        initialize_advanced_ai()
    return _faiss_dedup


def get_embedder():
    """Get embedder (ensures initialization)"""
    global _embedder, _initialized
    if not _initialized:
        initialize_advanced_ai()
    return _embedder


def train_ml_model_from_leads(leads: List[Dict[str, Any]]) -> bool:
    """
    Module-level helper: train (or re-train) the ML scoring model.
    Pass a list of lead dicts that each have a 'qualification_score' field.
    Returns True on success.
    """
    global _ml_model, _initialized
    if not _initialized:
        initialize_advanced_ai()
    if _ml_model is None:
        _ml_model = XGBLeadScoringModel()
    return _ml_model.train_from_leads(leads)


def initialize_advanced_ai():
    """
    Initialize all AI components (THREAD-SAFE)
    Uses double-check locking pattern to avoid race conditions
    """
    global _ollama_client, _spacy_nlp, _ml_model, _faiss_dedup, _embedder, _initialized

    # Quick check before acquiring lock (performance optimization)
    if _initialized:
        return

    # Acquire lock for initialization
    with _init_lock:
        # Double-check after acquiring lock
        if _initialized:
            return

        logger.info("=" * 80)
        logger.info("INITIALIZING ADVANCED AI STACK (THREAD-SAFE)")
        logger.info("=" * 80)

        # 1. Try Ollama - LLM Engine
        try:
            logger.info("[1/5] Initializing Ollama LLM...")
            _ollama_client = initialize_ollama()
            if _ollama_client:
                logger.info("✓ Ollama initialized successfully")
            else:
                logger.warning("⚠ Ollama not available - LLM scoring disabled")
        except Exception as e:
            logger.error(f"✗ Ollama initialization failed: {str(e)}")

        # 2. spaCy - NLP Processing
        try:
            logger.info("[2/5] Initializing spaCy NLP...")
            _spacy_nlp = initialize_spacy()
            if _spacy_nlp:
                logger.info("✓ spaCy initialized successfully")
            else:
                logger.warning("⚠ spaCy not available - NLP entity extraction disabled")
        except Exception as e:
            logger.error(f"✗ spaCy initialization failed: {str(e)}")

        # 3. XGBoost ML Model (30 features, Optuna-tuned, SHAP-explained)
        try:
            logger.info("[3/5] Initializing XGBoost ML model...")
            _ml_model = XGBLeadScoringModel()
            _ml_model.load_model()
            if _ml_model.model is not None:
                logger.info("✓ XGBoost ML model loaded successfully")
            else:
                logger.info("⚠ No saved model — auto-training from synthetic data in background")
                def _bootstrap_train(_m=_ml_model):
                    try:
                        ok = _m.train_from_leads([])
                        if ok:
                            logger.info("✓ ML model ready — synthetic bootstrap complete")
                        else:
                            logger.warning("⚠ ML synthetic bootstrap training failed")
                    except Exception as _bt_err:
                        logger.error(f"✗ ML bootstrap error: {_bt_err}")
                _bt = threading.Thread(target=_bootstrap_train, name="ml-bootstrap", daemon=True)
                _bt.start()
        except Exception as e:
            logger.error(f"✗ ML model initialization failed: {str(e)}")
            _ml_model = None

        # 4. Sentence-Transformers - Embeddings
        try:
            logger.info("[4/5] Initializing sentence-transformers embedder...")
            _embedder = initialize_embedder()
            if _embedder:
                logger.info("✓ Embedder initialized successfully")
            else:
                logger.warning("⚠ Embedder not available - vector embeddings disabled")
        except Exception as e:
            logger.error(f"✗ Embedder initialization failed: {str(e)}")

        # 5. FAISS - Vector Search & Deduplication
        try:
            logger.info("[5/5] Initializing FAISS deduplicator...")
            _faiss_dedup = FAISSDeduplicator()
            _faiss_dedup.load_index()
            if _faiss_dedup.index is not None:
                logger.info("✓ FAISS index loaded successfully")
            else:
                _faiss_dedup.initialize_index()
                if _faiss_dedup.index is not None:
                    logger.info("✓ FAISS index created (fresh)")
                else:
                    logger.warning("⚠ FAISS not available - deduplication disabled")
        except Exception as e:
            logger.error(f"✗ FAISS initialization failed: {str(e)}")
            _faiss_dedup = None

        # Mark initialization as complete (for thread-safety)
        _initialized = True

    logger.info("=" * 80)
    logger.info("Advanced AI Stack initialization complete (THREAD-SAFE)")
    logger.info(f"  Ollama:   {'✓' if _ollama_client else '✗'}")
    logger.info(f"  spaCy:    {'✓' if _spacy_nlp else '✗'}")
    logger.info(f"  ML model: {'✓' if (_ml_model and _ml_model.model is not None) else '✗'}")
    logger.info(f"  Embedder: {'✓' if _embedder else '✗'}")
    logger.info(f"  FAISS:    {'✓' if (_faiss_dedup and _faiss_dedup.index is not None) else '✗'}")
    logger.info("=" * 80)



def qualify_lead_advanced(lead_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Full 4-layer AI decision cascade (THREAD-SAFE).

    Layer 1 — QualificationAgent (rule-based analyzers, always runs)
               Weights: company_fit 20%, budget 20%, pain_points 30%,
                        contact_quality 15%, market_target 15%
    Layer 2 — ML Model (GradientBoosting, runs if trained model exists)
    Layer 3 — External LLM (Gemini → Groq → Ollama, runs if API key set)
    Layer 4 — FAISS duplicate check + spaCy entity extraction (enrichment)

    Score combination:
        If LLM available  → rule 30% + ML 20% + LLM 50%
        If ML only        → rule 50% + ML 50%
        If neither        → rule 100%

    Returns a rich dict with score, category, confidence, reasoning, and
    per-layer detail for full explainability.
    """
    # Collect singletons (lazy-init, thread-safe)
    spacy_nlp  = get_spacy_nlp()
    ml_model   = get_ml_model()
    faiss_dedup = get_faiss_dedup()
    embedder   = get_embedder()

    layers_used: List[str] = []
    details: Dict[str, Any] = {
        'rule_score': None,
        'ml_score': None,
        'ml_explanation': None,
        'llm_score': None,
        'llm_reasoning': None,
        'duplicates': [],
        'entities': {},
        'is_duplicate': False,
    }

    try:
        # ── Layer 1: QualificationAgent (rule-based, always available) ──────
        from app.services.qualification_agent import QualificationAgent
        qa = QualificationAgent()
        qa_result = qa.qualify_lead(lead_data)
        rule_score = float(qa_result.score)
        details['rule_score'] = rule_score
        details['rule_category'] = qa_result.category
        details['rule_reasoning'] = qa_result.reasoning
        details['recommendations'] = qa_result.recommendations
        layers_used.append('QualificationAgent')
        logger.debug(f"Layer1 rule score: {rule_score}")

        # ── Layer 2: ML Model ────────────────────────────────────────────────
        ml_score: Optional[float] = None
        if ml_model is not None and ml_model.model is not None:
            features = extract_features(lead_data)
            ml_expl = ml_model.predict_with_explanation(features)
            ml_score = float(ml_expl.get('score') or 0)
            details['ml_score'] = ml_score
            details['ml_explanation'] = ml_expl.get('top_factors')
            layers_used.append('ML(XGBoost)')
            logger.debug(f"Layer2 ML score: {ml_score}")

        # ── Layer 3: External LLM (Gemini → Groq → Ollama) ──────────────────
        llm_score: Optional[float] = None
        try:
            from app.services.gemini_service import get_ai_service
            ai_svc = get_ai_service()
            if ai_svc.is_available:
                llm_result = ai_svc.qualify_lead(lead_data)
                llm_score = float(llm_result.get('score', 0))
                details['llm_score'] = llm_score
                details['llm_reasoning'] = llm_result.get('reasoning', '')
                details['llm_strengths'] = llm_result.get('strengths', [])
                details['llm_weaknesses'] = llm_result.get('weaknesses', [])
                details['llm_next_action'] = llm_result.get('next_action', '')
                details['llm_provider'] = llm_result.get('ai_provider', '')
                layers_used.append(f"LLM({ai_svc.provider_name})")
                logger.debug(f"Layer3 LLM score: {llm_score}")
        except Exception as llm_err:
            logger.warning(f"LLM layer skipped: {llm_err}")

        # ── Combine scores with dynamic weighting ───────────────────────────
        if llm_score is not None and ml_score is not None:
            final_score = rule_score * 0.25 + ml_score * 0.25 + llm_score * 0.50
            confidence = 0.92
            method = 'rule+ml+llm'
        elif llm_score is not None:
            final_score = rule_score * 0.40 + llm_score * 0.60
            confidence = 0.85
            method = 'rule+llm'
        elif ml_score is not None:
            final_score = rule_score * 0.45 + ml_score * 0.55
            confidence = 0.78
            method = 'rule+ml'
        else:
            final_score = rule_score
            confidence = float(qa_result.confidence)
            method = 'rule_only'

        final_score = max(0.0, min(100.0, final_score))

        # ── Layer 4: FAISS duplicate check + spaCy NLP enrichment ───────────
        embedding = generate_lead_embedding(lead_data, embedder)
        if embedding is not None and faiss_dedup is not None:
            duplicates = faiss_dedup.find_duplicates(embedding)
            details['duplicates'] = duplicates
            if duplicates:
                details['is_duplicate'] = True
                logger.info(f"Duplicate detected: {duplicates}")

        text = f"{lead_data.get('name', '')} {lead_data.get('company', '')}"
        details['entities'] = extract_entities(text, spacy_nlp)

        # Store embedding for future dedup lookups
        if embedding is not None and faiss_dedup is not None:
            lead_id = lead_data.get('id') or f"lead_{lead_data.get('email', '')}"
            faiss_dedup.add_lead(str(lead_id), embedding)

        # ── Determine category ───────────────────────────────────────────────
        score_int = int(round(final_score))
        if score_int >= 80:
            category = 'Hot'
        elif score_int >= 60:
            category = 'Warm'
        else:
            category = 'Cold'

        return {
            'score': score_int,
            'category': category,
            'confidence': round(confidence, 2),
            'scoring_method': method,
            'layers_used': layers_used,
            'reason': details.get('llm_reasoning') or qa_result.reasoning.get('pain_points', {}).get('score', ''),
            'recommendations': details.get('recommendations', []),
            'next_action': details.get('llm_next_action', ''),
            'ai_provider': ' → '.join(layers_used),
            'details': details,
        }

    except Exception as e:
        logger.error(f"qualify_lead_advanced error: {e}", exc_info=True)
        return {
            'score': 50,
            'category': 'Warm',
            'confidence': 0.4,
            'scoring_method': 'error_fallback',
            'layers_used': layers_used,
            'reason': f'Error in AI cascade: {e}',
            'ai_provider': 'Error',
            'details': details,
        }
