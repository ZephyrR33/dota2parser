import argparse
import json
import os
from pathlib import Path
import sys

from . import APIError, DotaClient, InputError


def main():
    parser = argparse.ArgumentParser(description="Получение матчей Dota 2 через OpenDota")
    parser.add_argument("target", help="ID или ссылка на игрока; с --match — на матч")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--match", action="store_true", help="Получить подробности одного матча")
    mode.add_argument("--winrate", action="store_true", help="Винрейт за последние 20 игр (или --limit)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--hero-id", type=int)
    parser.add_argument("--output", type=Path, help="Сохранить JSON в файл")
    args = parser.parse_args()
    if args.winrate and (args.offset != 0 or args.hero_id is not None):
        parser.error("--winrate нельзя совмещать с --offset или --hero-id")
    client = DotaClient(api_key=os.getenv("OPENDOTA_API_KEY"), steam_api_key=os.getenv("STEAM_API_KEY"))
    try:
        if args.match:
            result = client.get_match(args.target)
        elif args.winrate:
            result = client.get_winrate(args.target, limit=args.limit if args.limit is not None else 20)
        else:
            result = client.get_matches(args.target, limit=args.limit if args.limit is not None else 100, offset=args.offset, hero_id=args.hero_id)
        output = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(output + "\n", encoding="utf-8")
        else:
            print(output)
    except (InputError, APIError, OSError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
