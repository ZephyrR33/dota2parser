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

В активированном виртуальном окружении **другого проекта** установите эту библиотеку из локальной папки:

```powershell
python -m pip install "C:\Users\IlyaKazorin\OneDrive\Документы\ChatGPT\dota2parser"
```

Для совместной разработки используйте editable-установку: изменения библиотеки будут сразу доступны другой программе без переустановки:

```powershell
python -m pip install -e "C:\Users\IlyaKazorin\OneDrive\Документы\ChatGPT\dota2parser"
```

На другом компьютере можно установить из GitHub после публикации репозитория (для приватного репозитория нужен доступ Git):

```powershell
python -m pip install "git+https://github.com/ZephyrR33/dota2parser.git"
```

Для воспроизводимой установки добавьте в `requirements.txt` другого проекта строку `dota2parser @ git+https://github.com/ZephyrR33/dota2parser.git@<commit-sha>`, заменив `<commit-sha>` на полный хеш опубликованного коммита. Затем выполните `python -m pip install -r requirements.txt`.

Создайте в другом проекте файл, например `dota_service.py`, и импортируйте публичный интерфейс (не называйте свой файл `dota2parser.py`, чтобы не перекрыть пакет):

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

### Винрейт за последние 20 игр

```python
from dota2parser import DotaClient

client = DotaClient()
stats = client.get_winrate("https://www.dotabuff.com/players/123456")
if stats["winrate"] is None:
    print("Нет матчей с известным результатом")
else:
    print(f"Винрейт: {stats['winrate']}%, побед: {stats['wins']}, поражений: {stats['losses']}")
```

Метод принимает те же ID и ссылки на игрока, что и `get_matches`. По умолчанию запрашивает последние 20 доступных API игр без фильтра по герою или результату. Для другого количества: `client.get_winrate(123456, limit=50)`.

Пример результата для 12 побед и 8 поражений:

```json
{
  "requested_matches": 20,
  "total_matches": 20,
  "counted_matches": 20,
  "wins": 12,
  "losses": 8,
  "unknown_matches": 0,
  "winrate": 60.0
}
```

Формула: `wins / counted_matches * 100`, округление до двух знаков. Если доступно меньше 20 игр, расчёт использует доступные игры. Матчи с неизвестным результатом остаются в `total_matches` и `unknown_matches`, но не входят в знаменатель; более старые игры вместо них не подгружаются. При отсутствии известных результатов `winrate` равен `None` (в JSON — `null`), а не 0%.

Через консоль:

```powershell
python -m dota2parser 123456 --winrate
python -m dota2parser 123456 --winrate --limit 20 --output winrate.json
```

Для асинхронной программы вызов можно вынести из цикла событий:

```python
import asyncio
from dota2parser import DotaClient

async def load_winrate(player):
    return await asyncio.to_thread(DotaClient().get_winrate, player)
```

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
