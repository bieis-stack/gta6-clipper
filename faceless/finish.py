"""Põe o gancho no vídeo do MoneyPrinterTurbo, envia-o para o Telegram e regista o tema.

Uso: python faceless/finish.py <pasta de saída do plan.py>

Lê TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID do ambiente e nunca os escreve no ecrã.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
STATE = HERE / "state.json"
FONT = HERE.parent / "assets" / "fonts" / "Anton-Regular.ttf"
HOOK_SECONDS = 3
MAX_BYTES = 49 * 1024 * 1024


def newest_video(home: Path) -> Path:
    videos = sorted((home / "storage" / "tasks").glob("*/final-*.mp4"), key=lambda p: p.stat().st_mtime)
    if not videos:
        raise SystemExit("erro: o MoneyPrinterTurbo não produziu nenhum vídeo")
    return videos[-1]


def add_hook(src: Path, dst: Path, hook: str, work: Path) -> Path:
    """O gancho em letras grandes nos primeiros segundos. Se falhar, segue o vídeo original."""
    text_file = work / "hook.txt"
    text_file.write_text(hook, encoding="utf-8")
    font = FONT.as_posix().replace(":", "\\:")
    text = text_file.as_posix().replace(":", "\\:")
    draw = (
        f"drawtext=fontfile='{font}':textfile='{text}':fontsize=96:fontcolor=yellow:"
        "borderw=9:bordercolor=black:x=(w-tw)/2:y=h*0.22:"
        f"enable='lt(t,{HOOK_SECONDS})'"
    )
    command = [
        "ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", draw,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "copy",
        "-movflags", "+faststart", str(dst),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or not dst.exists():
        print(f"aviso: não foi possível pôr o gancho no vídeo: {result.stderr[-300:]}", file=sys.stderr)
        return src
    return dst


def telegram(method: str, token: str, **kwargs) -> None:
    response = requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=120, **kwargs)
    if response.status_code != 200:
        # A mensagem de erro do Telegram não tem o token; o URL tem, por isso não se mostra.
        raise SystemExit(f"erro: o Telegram recusou {method}: {response.text[:300]}")


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "faceless_out")
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        print("erro: faltam os Secrets do Telegram", file=sys.stderr)
        return 1
    plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))
    video = add_hook(newest_video(Path(os.environ["MPT_HOME"])), out / "final.mp4", plan["hook"], out)
    if video.stat().st_size > MAX_BYTES:
        print("erro: o vídeo passa do limite de 50 MB do Telegram", file=sys.stderr)
        return 1
    with open(video, "rb") as handle:
        telegram(
            "sendVideo",
            token,
            data={"chat_id": chat, "caption": plan["title"], "supports_streaming": "true",
                  "width": "1080", "height": "1920"},
            files={"video": ("video.mp4", handle, "video/mp4")},
        )
    telegram(
        "sendMessage",
        token,
        data={"chat_id": chat, "text": f"🤖 Vídeo do canal de factos\n\n{plan['description']}"},
    )
    done = json.loads(STATE.read_text(encoding="utf-8"))["done"] if STATE.exists() else []
    done.append(plan["subject"])
    STATE.write_text(json.dumps({"done": done}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"entregue: {plan['subject']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
