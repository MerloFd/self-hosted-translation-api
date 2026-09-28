# Self-Hosted Translation API on AWS Lambda

API de tradução multi-idioma, **self-hosted e gratuita** (sem custo por requisição de API paga
tipo DeepL/Google Translate), rodando como **AWS Lambda Container Image**, exposta via **Function
URL**. Traduz textos de 8 idiomas de origem para um idioma alvo (neste exemplo, português
brasileiro), com detecção automática de idioma.

**Sem LLM.** Isso não é um wrapper em cima de GPT/Claude/Gemini — é um serviço de tradução
neural clássico, propósito único, leve o suficiente pra rodar em CPU, dentro do limite de
memória/tempo de uma Lambda, sem GPU e sem custo de API por chamada.

## Por que não um LLM

| | Este projeto | Tradução via LLM |
|---|---|---|
| Modelo | 1 rede neural pequena e especialista **por par de idiomas** | 1 modelo generalista enorme |
| Custo por chamada | US$ 0 (compute próprio, já contabilizado no Lambda) | US$ por token, toda vez |
| Onde roda | CPU, ~2-3GB RAM | Geralmente precisa de API externa ou GPU |
| O que faz | Só traduz — determinístico, sem "criatividade" | Tradução é só uma das mil coisas que sabe fazer |
| Privacidade | Texto nunca sai do seu ambiente AWS | Depende do provedor do LLM |

Um LLM entende contexto e gera texto livre; aqui não tem prompt, não tem conversa — é
tradução determinística, um modelo treinado exclusivamente para um par de idiomas.

## Arquitetura

```
texto → langdetect (detecção de idioma)
      → tokenizer (SentencePiece)
      → CTranslate2 + modelo Opus-MT (int8)   [pivot via inglês se necessário]
      → texto no idioma alvo
```

| Peça | Papel |
|---|---|
| **[Opus-MT](https://github.com/Helsinki-NLP/Opus-MT)** (Helsinki-NLP, CC-BY) | Os modelos de tradução em si. Um modelo pequeno e especialista por par de idiomas — não um modelo único "que sabe tudo". |
| **[CTranslate2](https://github.com/OpenNMT/CTranslate2)** | Motor de inferência em C++, otimizado para CPU. É quem efetivamente traduz em runtime. |
| **PyTorch (torch)** | Usado **só no build**, para ler o modelo original (formato HuggingFace/PyTorch) e converter para o formato do CTranslate2. Não entra no runtime — é removido da imagem final. |
| **int8 (quantização)** | Cada peso do modelo (normalmente float32) vira inteiro de 8 bits + fator de escala. Modelo ~4x menor, inferência mais rápida em CPU, perda de qualidade mínima. Aplicado no momento da conversão (`convert.py`), é feature nativa do conversor do CTranslate2. |
| **Tokenizer (`transformers.AutoTokenizer` + SentencePiece)** | Converte texto ↔ tokens. Em runtime, `transformers` é usado só para isso — sem torch. |
| **langdetect** | Detecta o idioma de origem. Puro Python, sem numpy/torch (evita problemas de compatibilidade em ambiente serverless). |

### Roteamento (pivot por inglês)

Não existem modelos abertos de qualidade traduzindo direto de russo/chinês/grego/etc para
português — então o inglês funciona como hub, o padrão de mercado nesse cenário:

- **Inglês é direto:** `en → pb` (modelo `opus-mt-tc-big-en-pt`, token `>>pob<<` seleciona
  português **brasileiro** em vez do europeu).
- **Demais idiomas pivotam:** `X → en → pb` (2 chamadas ao motor).

### Por que o runtime final é pequeno (~2,7GB, dentro do limite de 10GB de imagem Lambda)

O build faz tudo em **uma única camada Docker**: instala torch (CPU-only) → converte os
modelos → desinstala torch → limpa cache. Se cada passo fosse uma camada separada, os bytes do
torch ficariam na imagem de qualquer forma (camadas Docker são cumulativas). Assim, o runtime
final carrega só `ctranslate2` + `transformers` (tokenizer) + `sentencepiece` + `langdetect`.

## Contrato da API

```
POST <Function URL>
{ "text": "...", "title": "...", "target": "pb" }
```
- `title` é opcional — útil quando você traduz um par texto+título (ex: um artigo com manchete)
  numa única chamada, mesmo idioma detectado pra ambos.
- `source` é opcional — se omitido, detecção automática.
- `target` sempre `"pb"` neste exemplo (troque pra outro alvo alterando `convert.py` e o token
  de idioma do modelo `en-<alvo>` usado, se existir).

```
→ 200 { "outcome": "translated", "translated_text": "...", "translated_title": "...", "detected_source": "es" }
→ 200 { "outcome": "already_target", "translated_text": "<original>", "detected_source": "pt" }
→ 200 { "outcome": "unsupported", "detected_source": "xx" }
→ 400 { "outcome": "bad_request", "error": "..." }
→ 500 { "outcome": "error", "error": "..." }
```

## Rodando local (RIE, simulando o filesystem read-only do Lambda)

```bash
docker build --provenance=false -t translation-api:local .

docker run -d --name t -p 9000:8080 \
  --read-only --tmpfs "/tmp:rw,size=512m" \
  -e HOME=/home/sbx_fake \
  translation-api:local
```

```powershell
.\test.ps1 -Text "Hello world" -Title "A quick headline"
```

> RIE local exige envelope `{"body": "..."}` (decode duplo); a Function URL em produção é
> direta (`{"text": ..., "target": ...}` sem envelope).
> PowerShell 5.1: `Invoke-RestMethod` manda o corpo em Latin-1 por padrão, corrompendo
> acentos/cirílico/CJK — `test.ps1` já contorna isso mandando bytes UTF-8 explícitos.

## Deploy (build → ECR → Lambda)

```bash
docker build --provenance=false -t translation-api:latest .

aws ecr get-login-password --region <sua-regiao> \
  | docker login --username AWS --password-stdin <conta>.dkr.ecr.<sua-regiao>.amazonaws.com

docker tag translation-api:latest <conta>.dkr.ecr.<sua-regiao>.amazonaws.com/translation-api:latest
docker push <conta>.dkr.ecr.<sua-regiao>.amazonaws.com/translation-api:latest

aws lambda update-function-code \
  --function-name <nome-da-funcao> \
  --image-uri <conta>.dkr.ecr.<sua-regiao>.amazonaws.com/translation-api:latest \
  --region <sua-regiao>
```

Configuração recomendada da função: **Container Image**, memória ≥ 2-3GB, timeout ≥ 5min
(cold start após deploy novo pode passar de 90s, por causa do pull de uma imagem de ~2,7GB).

Exponha via **Function URL** (`AuthType: NONE` é o mais simples para testar, mas não é
autenticação — para uso real, prefira `AWS_IAM` ou valide um header secreto no handler).

## Adicionando um idioma

Edite `convert.py`: adicione uma entrada em `CANDIDATES` com o(s) modelo(s) Helsinki-NLP
candidatos pro par `<idioma>-en` (o conversor tenta em ordem até um funcionar). Depois é só
rebuildar a imagem — o `Dockerfile` já converte tudo de novo no build.

```python
"ja-en": ["Helsinki-NLP/opus-mt-ja-en"],
```

E adicione o código do idioma em `_XEN` no `handler.py`.

**Lição aprendida (grego):** nem sempre o modelo "maior"/mais recente é melhor. O
`opus-mt-tc-big-el-en` degenera em saída de lixo pra esse par; o `opus-mt-grk-en` (menor, do
grupo de línguas gregas) funciona bem e é mais rápido. Sempre valide a saída de um par novo
antes de assumir que "só está lento".

## Números de performance (textos ~5k caracteres)

| Regime | Tempo | Quando |
|---|---|---|
| Cold start, 1ª chamada após deploy novo | ~90-100s | pull da imagem (~2,7GB) |
| Cold start após ociosidade (imagem já cacheada) | ~30-35s | após alguns minutos sem chamadas |
| 1ª tradução de cada idioma no container "quente" | ~35-45s | carrega o modelo do par na memória |
| Tradução seguinte, idioma já carregado | ~15-25s | |
| Frase curta, idioma já carregado | < 1s | |

## Limitações conhecidas

- Pivot por inglês (idiomas não-ingleses) pode gerar artefatos ocasionais — tradução dupla
  acumula um pouco de perda. Acima da qualidade de engines antigas (ex: Argos Translate), abaixo
  de serviços pagos (DeepL).
- Detecção de idioma é 1 idioma por texto — um trecho em idioma diferente do dominante (ex:
  rodapé em outro idioma) sai cru.
- Cold start é inerente ao Lambda — mitigável com Provisioned Concurrency (tem custo fixo) ou
  keep-warm via EventBridge, se o caso de uso não tolerar a latência.

## Créditos / licença

- Modelos [Helsinki-NLP/Opus-MT](https://github.com/Helsinki-NLP/Opus-MT) — licença **CC-BY 4.0**.
- Motor de inferência [OpenNMT/CTranslate2](https://github.com/OpenNMT/CTranslate2).
- Código deste repositório: MIT (ver `LICENSE`).
