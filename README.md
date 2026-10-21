# Dota 2 Parser

Python 3.10+, без внешних зависимостей. Библиотека для внедрения в другую программу и CLI для выгрузки JSON. Получает статистику через [OpenDota API](https://docs.opendota.com/), а не разбирает HTML или файлы реплеев `.dem`.

## Запуск

Из папки проекта:

```powershell
python -m dota2parser 123456 --limit 20 --output matches.json
python -m dota2parser "https://www.dotabuff.com/players/123456" --limit 50
python -m dota2parser "https://www.opendota.com/matches/8000000000" --match --output match.json
```

Можно установить пакет через `python -m pip install .`, после чего доступна команда `dota2parser`.

## Внедрение

```python
from dota2parser import DotaClient, APIError, InputError

client = DotaClient(timeout=30, retries=3)
try:
    matches = client.get_matches("https://www.opendota.com/players/123456", limit=20)
    for match in matches:
        print(match["match_id"], match.get("hero_id"), match["won"])
    if matches:
        details = client.get_match(matches[0]["match_id"])
except InputError as exc:
    print("Неверный ввод:", exc)
except APIError as exc:
    print("Ошибка сервиса:", exc, "HTTP:", exc.status)
```

`get_matches(player, limit=100, offset=0, hero_id=None, win=None)` возвращает список словарей. Поля OpenDota сохраняются: `match_id`, `start_time` (Unix UTC), `duration` (секунды), `hero_id`, `kills`, `deaths`, `assists` и другие доступные поля. Дополнительно вычисляются `is_radiant` и `won`; если данных недостаточно, значение `None`. Состав полей зависит от ответа API: используйте `.get()` для необязательных полей.

`get_match(id_or_url)` возвращает словарь подробностей матча, включая доступные данные игроков. Это отдельный запрос: библиотека не загружает подробности каждого матча автоматически.

Поддерживаются Dota account ID (ID друга), SteamID64, ссылки `steamcommunity.com/profiles/...`, `opendota.com/players/...`, `dotabuff.com/players/...`. `userid` здесь означает постоянный ID аккаунта, а не временный номер участника игрового сервера. Никнейм сам по себе не является уникальным ID.

Для именной ссылки `steamcommunity.com/id/...` нужен [Steam Web API key](https://steamcommunity.com/dev/apikey), используемый через [ResolveVanityURL](https://partner.steamgames.com/doc/webapi/ISteamUser#ResolveVanityURL):

```powershell
$env:STEAM_API_KEY = "your-key"
# Необязательный ключ OpenDota:
$env:OPENDOTA_API_KEY = "your-key"
```

В Python передайте ключи явно: `DotaClient(steam_api_key="...", api_key="...")`. CLI читает указанные переменные окружения. Не сохраняйте ключи в исходном коде.

## Ограничения

Возвращаются только доступные OpenDota данные; полнота истории и наличие подробной статистики не гарантируются. Пустой список означает отсутствие доступных матчей, но сам по себе не доказывает, что профиль закрыт. Недоступные данные закрытого профиля инструмент не восстанавливает.

`limit` — максимальное число результатов, а не обещание получить столько матчей. Запросы выполняются последовательно, с интервалом по умолчанию 1.1 с. При HTTP 429 и временных серверных/сетевых ошибках выполняются ограниченные повторы; слишком длинный `Retry-After` возвращает `APIError`. Учитывайте актуальные ограничения своего тарифа OpenDota. Пагинация через offset не является снимком: при появлении новых матчей возможен сдвиг страниц, дубликаты внутри одной загрузки удаляются.

Клиент синхронный: для GUI запускайте в рабочем потоке, для asyncio — через `asyncio.to_thread`. Создавайте отдельный экземпляр для каждого рабочего потока. Результаты можно сериализовать через `json.dumps` или передать непосредственно другой Python-программе.

## Проверка

```powershell
python -m unittest discover -s tests -v
```

Тесты используют подменённые ответы API и не требуют сети или ключей.
