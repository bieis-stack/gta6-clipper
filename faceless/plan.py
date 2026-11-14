"""Escolhe o próximo vídeo e escreve a configuração do MoneyPrinterTurbo.

Uso: python faceless/plan.py <pasta de saída>

Primeiro usa os vídeos escritos à mão em topics.yaml (factos verificados).
Quando acabarem, pede um vídeo novo a uma IA gratuita: o GitHub Models (com
GITHUB_MODELS_TOKEN, o token do próprio workflow) e, se falhar, o Pollinations
(sem chave). Se a IA falhar, repete um vídeo da lista. O plano gratuito do
Gemini não existe na Europa.

Lê PIXABAY_API_KEY (ou PEXELS_API_KEY) do ambiente e nunca a escreve no ecrã.
Escreve em <pasta>/plan.json o tema, o gancho, o título, o guião, as palavras
de pesquisa e a descrição, e em $MPT_HOME/config.toml a configuração.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import requests
import yaml

HERE = Path(__file__).resolve().parent
STATE = HERE / "state.json"
TOPICS = HERE / "topics.yaml"
MODELS_BASE_URL = "https://models.github.ai/inference"
MODEL = os.environ.get("GITHUB_MODEL", "openai/gpt-4.1-mini")
# Grátis e sem chave, compatível com a OpenAI. É lento (até ~90 s por pedido).
POLLINATIONS_BASE_URL = "https://text.pollinations.ai/openai"
POLLINATIONS_MODEL = "openai"
HASHTAGS = "#miami #florida #vicecity #gta6 #facts #shorts"
FIELDS = ("subject", "hook", "title", "script", "terms")

PROMPT = """You plan one vertical short video (about 30 seconds) for a faceless \
YouTube Shorts / TikTok channel. Niche: {niche}
Audience: 13 to 20 years old, scrolling fast. Pick a topic that makes them stop.
Only real, well-known, verifiable facts: if you are not sure of a fact, leave it \
out. No private people, no crimes by named people, no medical or financial advice.

Topics already done (do not repeat or rephrase them):
{done}

Answer with JSON only:
{{"subject": "the topic in one sentence",
  "hook": "on-screen hook, 2 to 6 words, ALL CAPS, no emojis",
  "title": "upload title, at most 60 characters, curiosity, may end with one emoji",
  "script": "60 to 90 words read aloud; the first sentence is the hook; short \
sentences; end with a question for the comments",
  "terms": "3 comma-separated stock footage search terms in English"}}"""


def _clean_hook(text) -> str | None:
    if not isinstance(text, str):
        return None
    text = re.sub(r"[^A-Z0-9 '!?.,&$%-]", "", text.upper())
    text = " ".join(text.split())
    return text if 2 <= len(text.split()) <= 7 and len(text) <= 40 else None


def _chat(base_url: str, model: str, token: str, prompt: str) -> dict:
    response = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {token or 'free'}"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}]},
        timeout=90,
    )
    response.raise_for_status()
    text = response.json()["choices"][0]["message"]["content"]
    return json.loads(text[text.find("{") : text.rfind("}") + 1])


def _ask(prompt: str, token: str) -> dict:
    """GitHub Models (com o token do workflow) e, se falhar, Pollinations."""
    services = [("GitHub Models", MODELS_BASE_URL, MODEL, token)] if token else []
    services.append(("Pollinations", POLLINATIONS_BASE_URL, POLLINATIONS_MODEL, ""))
    for index, (name, base_url, model, key) in enumerate(services):
        try:
            return _chat(base_url, model, key, prompt)
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as error:
            print(f"aviso: o {name} falhou ({type(error).__name__})", file=sys.stderr)
            if index == len(services) - 1:
                raise
    raise ValueError("sem serviços de IA")


def _tidy(entry: dict) -> dict:
    return {key: " ".join(str(entry[key]).split()) for key in FIELDS}


def _from_ai(data: dict, done: list[str]) -> dict | None:
    subject = str(data.get("subject", "")).strip()
    hook = _clean_hook(data.get("hook"))
    script = " ".join(str(data.get("script", "")).split())
    terms = str(data.get("terms", "")).strip()
    if not (subject and hook and terms and 50 <= len(script.split()) <= 110) or subject in done:
        return None
    title = str(data.get("title", "")).strip()[:70] or subject[:70]
    return {"subject": subject, "hook": hook, "title": title, "script": script, "terms": terms}


def choose(niche: str, seeds: list[dict], done: list[str], token: str) -> dict:
    """Os vídeos escritos à mão primeiro (factos verificados); depois a IA."""
    for seed in seeds:
        if seed["subject"] not in done:
            return _tidy(seed)
    prompt = PROMPT.format(niche=niche, done="\n".join(f"- {t}" for t in done[-60:]) or "- none")
    try:
        plan = _from_ai(_ask(prompt, token), done)
        if plan:
            return plan
        print("aviso: a IA deu um vídeo inválido; a repetir um da lista", file=sys.stderr)
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as error:
        print(f"aviso: a IA falhou ({type(error).__name__}); a repetir um da lista",
              file=sys.stderr)
    return _tidy(seeds[len(done) % len(seeds)])


def toml_string(value: str) -> str:
    return json.dumps(value)  # uma string JSON é uma string TOML básica válida


def write_config(home: Path, source: str, footage_key: str) -> None:
    home.mkdir(parents=True, exist_ok=True)
    lines = [
        "[app]",
        f"video_source = {toml_string(source)}",
        f"{source}_api_keys = [{toml_string(footage_key)}]",
        # Só é usado se faltar o guião; o guião vem sempre do plan.json.
        'llm_provider = "openai"',
        'openai_api_key = "free"',
        f"openai_base_url = {toml_string(POLLINATIONS_BASE_URL)}",
        f"openai_model_name = {toml_string(POLLINATIONS_MODEL)}",
        'subtitle_provider = "edge"',
    ]
    (home / "config.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "faceless_out")
    token = os.environ.get("GITHUB_MODELS_TOKEN", "").strip()
    # O Pexels suspendeu as chaves novas (novembro de 2026); o Pixabay serve igual.
    pexels_key = os.environ.get("PEXELS_API_KEY", "").strip()
    pixabay_key = os.environ.get("PIXABAY_API_KEY", "").strip()
    source, footage_key = ("pexels", pexels_key) if pexels_key else ("pixabay", pixabay_key)
    if not footage_key:
        print("erro: falta o Secret PIXABAY_API_KEY no repositório", file=sys.stderr)
        return 1
    topics = yaml.safe_load(TOPICS.read_text(encoding="utf-8"))
    done = json.loads(STATE.read_text(encoding="utf-8"))["done"] if STATE.exists() else []
    plan = choose(topics["niche"], topics["seeds"], done, token)
    plan["description"] = f"{plan['title']}\n\n{HASHTAGS}"
    plan["source"] = source
    out.mkdir(parents=True, exist_ok=True)
    (out / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    write_config(Path(os.environ["MPT_HOME"]), source, footage_key)
    print(f"tema: {plan['subject']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
