import os
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
from ctranslate2.converters import TransformersConverter
from transformers import AutoTokenizer

# Idioma alvo fixo neste exemplo: português brasileiro (pb / >>pob<<).
# Troque TARGET_LANG e os pares abaixo pra apontar pra outro idioma alvo.
TARGET_LANG = "pt"

# Cada par tenta candidatos em ordem (bilingual -> tc-big) até um funcionar.
# Adicionar um idioma novo = adicionar uma entrada aqui (ver README "Adicionando um idioma").
CANDIDATES = {
    "en-pt": ["Helsinki-NLP/opus-mt-tc-big-en-pt"],
    "es-en": ["Helsinki-NLP/opus-mt-es-en", "Helsinki-NLP/opus-mt-tc-big-es-en"],
    "it-en": ["Helsinki-NLP/opus-mt-it-en", "Helsinki-NLP/opus-mt-tc-big-itc-en"],
    "fr-en": ["Helsinki-NLP/opus-mt-fr-en", "Helsinki-NLP/opus-mt-tc-big-fr-en"],
    "de-en": ["Helsinki-NLP/opus-mt-de-en", "Helsinki-NLP/opus-mt-tc-big-de-en"],
    "ru-en": ["Helsinki-NLP/opus-mt-ru-en", "Helsinki-NLP/opus-mt-tc-big-ru-en"],
    "zh-en": ["Helsinki-NLP/opus-mt-zh-en", "Helsinki-NLP/opus-mt-tc-big-zh-en"],
    "el-en": ["Helsinki-NLP/opus-mt-grk-en"],  # grego: grk-en funciona bem; tc-big-el-en degenera em lixo, evitar
}

ok = {}
for pair, cands in CANDIDATES.items():
    done = False
    for m in cands:
        try:
            d = f"/opt/ct2/{pair}"
            TransformersConverter(m).convert(d, quantization="int8", force=True)
            AutoTokenizer.from_pretrained(m).save_pretrained(d)
            print(f"OK {pair} <- {m}", flush=True)
            ok[pair] = m
            done = True
            break
        except Exception as e:
            print(f"FALHOU {pair} <- {m}: {str(e)[:120]}", flush=True)
    if not done:
        print(f"### SEM MODELO para {pair}", flush=True)

print("CONVERTIDOS:", ok, flush=True)
