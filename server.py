from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from translator import translate_request

app = FastAPI(title="Self-Hosted Translation API")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/translate")
async def translate(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"outcome": "bad_request", "error": "JSON inválido"})

    status, payload = translate_request(body)
    return JSONResponse(status_code=status, content=payload)
