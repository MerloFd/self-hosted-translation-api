FROM public.ecr.aws/lambda/python:3.12

COPY translator.py ${LAMBDA_TASK_ROOT}/translator.py
COPY handler.py ${LAMBDA_TASK_ROOT}/handler.py
COPY convert.py /tmp/convert.py

# Uma camada: instala (torch só p/ conversão) -> converte modelos Opus-MT->CT2 int8 -> remove torch.
# Runtime final fica só com ctranslate2 + transformers (tokenizer, sem torch) + sentencepiece + langdetect.
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir ctranslate2 transformers sentencepiece sacremoses langdetect \
 && python3 /tmp/convert.py \
 && pip uninstall -y torch sympy networkx mpmath \
 && rm -rf /root/.cache /tmp/* /var/cache/* \
 && python3 -c "import ctranslate2, transformers, sentencepiece, langdetect; print('runtime deps OK (sem torch)')"

CMD ["handler.lambda_handler"]
