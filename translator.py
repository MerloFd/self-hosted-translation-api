import os
import re

os.environ["HF_HUB_OFFLINE"] = "1"      # sem rede em runtime
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import ctranslate2
from transformers import AutoTokenizer

try:
    from langdetect import detect as _ld, DetectorFactory
    DetectorFactory.seed = 0
except Exception:
    _ld = None

CT2 = os.environ.get("CT2_DIR", "/opt/ct2")
_tok, _tr = {}, {}


def _load(pair):
    if pair not in _tr:
        d = f"{CT2}/{pair}"
        _tok[pair] = AutoTokenizer.from_pretrained(d)
        _tr[pair] = ctranslate2.Translator(d, intra_threads=0)
    return _tok[pair], _tr[pair]


def _split(text):
    # reconhece pontuação latina, grega (; ·) e CJK (。)
    parts = re.split(r'(?<=[.!?;·。])\s+', text.strip())
    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # quebra pedaços longos (evita sequência > limite de 512 tokens do modelo)
        while len(p) > 350:
            cut = p.rfind(' ', 0, 350)
            if cut <= 0:
                cut = 350
            out.append(p[:cut].strip())
            p = p[cut:].strip()
        if p:
            out.append(p)
    return out or [text]


def _translate(pair, text, prefix=""):
    tok, tr = _load(pair)
    sents = _split(text)
    src = [tok.convert_ids_to_tokens(tok.encode(prefix + s)) for s in sents]
    res = tr.translate_batch(src, max_batch_size=16, beam_size=4)
    return " ".join(
        tok.decode(tok.convert_tokens_to_ids(r.hypotheses[0]), skip_special_tokens=True)
        for r in res
    )


_MAP = {"zh-cn": "zh", "zh-tw": "zh"}
_XEN = {"es", "it", "fr", "de", "ru", "zh", "el"}  # tem par X->en convertido (ver convert.py)
_ALREADY = {"pt", "pb"}                              # já é o idioma alvo -> passthrough


def _detect(text):
    if not _ld:
        return None
    try:
        c = _ld(" ".join(text.split())[:2000])
    except Exception:
        return None
    return _MAP.get(c, c)


def _translate_pair(src, text):
    # src já resolvido (mapeado); retorna None se não há modelo pro idioma
    if src == "en":
        return _translate("en-pt", text, prefix=">>pob<< ")  # >>pob<< = português brasileiro
    if src in _XEN:
        en = _translate(f"{src}-en", text)                # X -> en
        return _translate("en-pt", en, prefix=">>pob<< ")  # en -> alvo
    return None


def translate_request(body: dict) -> tuple[int, dict]:
    """
    Regra de negócio pura, sem nenhuma dependência de Lambda/HTTP.
    Recebe o corpo já parseado (dict) e devolve (status_http, payload).
    Usado tanto pelo handler.py (Lambda) quanto pelo server.py (backend tradicional).
    """
    if not isinstance(body, dict):
        return 400, {"outcome": "bad_request", "error": "corpo deve ser objeto JSON"}

    original = body.get("text") or ""
    text = original.strip()
    original_title = body.get("title") or ""
    title = original_title.strip()
    target = body.get("target") or ""
    if not text or not target:
        return 400, {"outcome": "bad_request",
                     "error": "campos 'text' e 'target' são obrigatórios"}

    src = body.get("source") or ""
    if not src or src == "auto":
        src = _detect(text) or ""
    src = _MAP.get(src, src)

    try:
        # já está no idioma alvo -> passthrough (devolve o texto original)
        if src in _ALREADY:
            return 200, {"outcome": "already_target",
                         "translated_text": original,
                         "translated_title": original_title,
                         "detected_source": src}
        out = _translate_pair(src, text)
        if out is None:
            # idioma detectado sem modelo -> resultado de negócio (não é erro técnico)
            return 200, {"outcome": "unsupported", "detected_source": src or None}
        out_title = _translate_pair(src, title) if title else ""
    except Exception as e:
        return 500, {"outcome": "error", "error": str(e)}

    return 200, {"outcome": "translated",
                 "translated_text": out,
                 "translated_title": out_title,
                 "detected_source": src}
