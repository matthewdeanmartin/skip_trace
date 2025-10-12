# skip_trace/analysis/ner.py
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import spacy
from spacy.language import Language

SPACY_AVAILABLE = True


logger = logging.getLogger(__name__)

_nlp: Optional[Language] = None


def _get_nlp_model() -> Optional[Language]:
    """Loads and caches the spaCy model. Returns None if unavailable."""
    global _nlp
    if not SPACY_AVAILABLE:
        return None
    if _nlp is None:
        try:
            logger.debug("Loading spaCy model 'en_core_web_sm'...")
            _nlp = spacy.load("en_core_web_sm")
            logger.info("Successfully loaded spaCy NER model.")
        except IOError:
            logger.warning(
                "spaCy is installed, but model 'en_core_web_sm' not found. "
                "Run 'python -m spacy download en_core_web_sm' to install it."
            )
            return None
    return _nlp


def extract_entities(text: str) -> List[Tuple[str, str]]:
    """
    Extracts person and organization entities from a string using spaCy.

    Args:
        text: The text to process.

    Returns:
        A list of tuples, where each tuple is (entity_text, entity_label).
        Returns an empty list if spaCy is not available or fails.
    """
    nlp = _get_nlp_model()
    if not nlp:
        return []

    doc = nlp(text)
    entities = []
    for ent in doc.ents:
        if ent.label_ in ["PERSON", "ORG"]:
            entities.append((ent.text.strip(), ent.label_))
            logger.debug(f"NER found entity: '{ent.text}' (Label: {ent.label_})")
    return entities
