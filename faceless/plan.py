"""Escolhe o tema do próximo vídeo e escreve a configuração do MoneyPrinterTurbo.

Uso: python faceless/plan.py <pasta de saída>

Lê GEMINI_API_KEY e PIXABAY_API_KEY (ou PEXELS_API_KEY) do ambiente e nunca as escreve no ecrã.
Escreve em <pasta>/plan.json o tema, o gancho, o título e a descrição, e em
$MPT_HOME/config.toml a configuração do MoneyPrinterTurbo.
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
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
HASHTAGS = "#miami #florida #vicecity #gta6 #facts #shorts"

PROMPT = """You plan one vertical short video (about 30 seconds) for a faceless \
YouTube Shorts / TikTok channel. Niche: {niche}
Audience: 13 to 20 years old, scrolling fast. Pick a topic that makes them stop.
The topic must be about real, well-known, verifiable facts. No private people, \
no crimes by named people, no medical or financial advice.

Topics already done (do not repeat or rephrase them):
{done}

Answer with JSON only:
{{"subject": "the topic in one sentence",
  "hook": "on-screen hook, 2 to 6 words, ALL CAPS, no emojis",
  "title": "upload title, at most 60 characters, curiosity, may end with one emoji",
  "description": "one or two sentences for the description, no hashtags"}}"""


def _clean_hook(text) -> str | None:
    if not isinstance(text, str):
        return None
    text = re.sub(r"[^A-Z0-9 '!?.,&$%-]", "", text.upper())
    text = " ".join(text.split())
    return text if 2 <= len(text.split()) <= 7 and len(text) <= 40 else None


def _ask(prompt: str, key: str) -> dict:
    response = requests.post(
        GEMINI_URL.format(model=MODEL),
        headers={"x-goog-api-key": key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 1.0},
        },
        timeout=30,
    )
    response.raise_for_status()
    text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text[text.find("{") : text.rfind("}") + 1])


def choose(niche: str, seeds: list[str], done: list[str], key: str) -> dict:
    prompt = PROMPT.format(niche=niche, done="\n".join(f"- {t}" for t in done[-60:]) or "- none")
    try:
        data = _ask(prompt, key)
        subject = str(data.get("subject", "")).strip()
        hook = _clean_hook(data.get("hook"))
        if subject and hook and subject not in done:
            return {
                "subject": subject,
                "hook": hook,
                "title": str(data.get("title", "")).strip()[:70] or subject[:70],
                "description": str(data.get("description", "")).strip(),
            }
        print("aviso: a IA deu um tema inválido; a usar a lista", file=sys.stderr)
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as error:
        print(f"aviso: a IA não escolheu o tema ({type(error).__name__}); a usar a lista",
              file=sys.stderr)
    fresh = [seed for seed in seeds if seed not in done]
    subject = fresh[0] if fresh else seeds[len(done) % len(seeds)]
    return {"subject": subject, "hook": "YOU DIDN'T KNOW THIS", "title": subject[:70],
            "description": ""}


def toml_string(value: str) -> str:
    return json.dumps(value)  # uma string JSON é uma string TOML básica válida


def write_config(home: Path, gemini_key: str, source: str, footage_key: str) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(
        "[app]\n"
        f"video_source = {toml_string(source)}\n"
        f"{source}_api_keys = [{toml_string(footage_key)}]\n"
        'llm_provider = "gemini"\n'
        f"gemini_api_key = {toml_string(gemini_key)}\n"
        f"gemini_model_name = {toml_string(MODEL)}\n"
        'subtitle_provider = "edge"\n',
        encoding="utf-8",
    )


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "faceless_out")
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    # O Pexels suspendeu as chaves novas (novembro de 2026); o Pixabay serve igual.
    pexels_key = os.environ.get("PEXELS_API_KEY", "").strip()
    pixabay_key = os.environ.get("PIXABAY_API_KEY", "").strip()
    source, footage_key = ("pexels", pexels_key) if pexels_key else ("pixabay", pixabay_key)
    missing = [name for name, value in (("GEMINI_API_KEY", gemini_key),
                                        ("PIXABAY_API_KEY", footage_key)) if not value]
    if missing:
        print(f"erro: faltam os Secrets {', '.join(missing)} no repositório", file=sys.stderr)
        return 1
    topics = yaml.safe_load(TOPICS.read_text(encoding="utf-8"))
    done = json.loads(STATE.read_text(encoding="utf-8"))["done"] if STATE.exists() else []
    plan = choose(topics["niche"], topics["seeds"], done, gemini_key)
    plan["description"] = "\n\n".join(p for p in (plan["description"], HASHTAGS) if p)
    out.mkdir(parents=True, exist_ok=True)
    plan["source"] = source
    (out / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    write_config(Path(os.environ["MPT_HOME"]), gemini_key, source, footage_key)
    print(f"tema: {plan['subject']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
