"""Keep ownership scanning usable when the optional native NLP stack is absent."""

import builtins
import importlib


def test_ner_without_spacy(monkeypatch):
    from skip_trace.analysis import ner

    original_import = builtins.__import__

    def without_spacy(name, *args, **kwargs):
        if name == "spacy" or name.startswith("spacy."):
            raise ImportError("spaCy wheel is unavailable")
        return original_import(name, *args, **kwargs)

    try:
        with monkeypatch.context() as context:
            context.setattr(builtins, "__import__", without_spacy)
            importlib.reload(ner)
            assert not ner.SPACY_AVAILABLE
            assert ner.extract_entities("Copyright Matthew Martin") == []
    finally:
        importlib.reload(ner)
