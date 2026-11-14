"""Escolhe o tema do próximo vídeo e escreve a configuração do MoneyPrinterTurbo.

Uso: python faceless/plan.py <pasta de saída>

Lê GITHUB_MODELS_TOKEN (o token do próprio workflow, para o GitHub Models,
gratuito) e PIXABAY_API_KEY (ou PEXELS_API_KEY) do ambiente, e nunca os
escreve no ecrã. O plano gratuito do Gemini não existe na Europa.
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
MODELS_BASE_URL = "https://models.github.ai/inference"
MODEL = os.environ.get("GITHUB_MODEL", "openai/gpt-4.1-mini")
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


def _ask(prompt: str, token: str) -> dict:
    response = requests.post(
        f"{MODELS_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={"model": MODEL, "temperature": 1.0,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=30,
    )
    if response.status_code != 200:
        print(f"aviso: o GitHub Models respondeu {response.status_code}: {response.text[:200]}",
              file=sys.stderr)
    response.raise_for_status()
    text = response.json()["choices"][0]["message"]["content"]
    return json.loads(text[text.find("{") : text.rfind("}") + 1])


def choose(niche: str, seeds: list[str], done: list[str], token: str) -> dict:
    prompt = PROMPT.format(niche=niche, done="\n".join(f"- {t}" for t in done[-60:]) or "- none")
    try:
        data = _ask(prompt, token)
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


def write_config(home: Path, token: str, source: str, footage_key: str) -> None:
    home.mkdir(parents=True, exist_ok=True)
    lines = [
        "[app]",
        f"video_source = {toml_string(source)}",
        f"{source}_api_keys = [{toml_string(footage_key)}]",
        # O GitHub Models fala o mesmo protocolo da OpenAI.
        'llm_provider = "openai"',
        f"openai_api_key = {toml_string(token)}",
        f"openai_base_url = {toml_string(MODELS_BASE_URL)}",
        f"openai_model_name = {toml_string(MODEL)}",
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
    missing = [name for name, value in (("GITHUB_MODELS_TOKEN", token),
                                        ("PIXABAY_API_KEY", footage_key)) if not value]
    if missing:
        print(f"erro: faltam {', '.join(missing)}", file=sys.stderr)
        return 1
    topics = yaml.safe_load(TOPICS.read_text(encoding="utf-8"))
    done = json.loads(STATE.read_text(encoding="utf-8"))["done"] if STATE.exists() else []
    plan = choose(topics["niche"], topics["seeds"], done, token)
    plan["description"] = "\n\n".join(p for p in (plan["description"], HASHTAGS) if p)
    plan["source"] = source
    out.mkdir(parents=True, exist_ok=True)
    (out / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    write_config(Path(os.environ["MPT_HOME"]), token, source, footage_key)
    print(f"tema: {plan['subject']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
