# Hermes: продолжение Close Call, stage 2

Подготовлено 2026-09-26. Готово для read-only исследований. **EXECUTION_DISABLED**; готовность к реальному участию не заявляется.

## Рабочая копия и provenance

Продолжать существующую папку, не клонировать заново:
`C:\Users\razgl\Documents\Codex\2026-09-26\files-pasted-by-the-user-ai\outputs\flop-close-call`.

- Ветка: `local/read-only-tooling`; её точный текущий SHA: `git rev-parse HEAD` (отчёт о commit вынесен за commit, чтобы избежать самоссылки).
- `upstream`: https://github.com/flop-labs/technocore-close-call-challenge.git
- `origin`: https://github.com/Ahmsak/flop-close-call-agent.git
- Официальный candidate commit: `66c1da36538e4b1c685417d2f66922906b13fea0`; тег `close-1` совпал. Manifest SHA-256: `bae09812e25eb6f1369c611f24964f7ea0acafddfc45301a16f33f941296dafa`.
- Это обычный собственный repository с сохранением исходной Git history, не GitHub fork. LICENSE/NOTICE и manifest-covered artifacts сохранены.
- GitHub repository создан пустым private, затем по запросу пользователя переведён в **PUBLIC**. После подтверждения пользователем email reauthentication настройки GitHub показывают «This repository is currently public». Git credentials отдельно недоступны: браузерный вход не авторизует Git. Push пока не выполнен, remote commit SHA отсутствует. Не выдавать локальный SHA за pushed SHA.
- Старые stage 1 отчёты сохранены как история. Этот handoff и STAGE2_REPORT имеют приоритет по текущему состоянию. Не считать прежние условные 08:45/08:50 UTC безопасными дедлайнами.

## Команды из корня repository

Существующий `.venv` уже подготовлен. Для переноса на новую машину:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r tools/requirements-verification.txt
```

```powershell
python scripts/verify.py
python scripts/build.py --check
python -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest discover -s local_tests -v
.\.venv\Scripts\python.exe -m tools.contest_client.observer
python -m tools.research_scenarios --final-comparison --snapshot data/observer/latest.json
python tools/simulate_strategy.py tools/example_scenario.json
python tools/audit_history.py
```

Observer: один проход fetch → signature/package/order checks → atomic snapshot → компактный вывод. Прямые источники: `https://technocore.chat/r/{room}/export`, room из фиксированного списка `d-close1-price`, `d-close1-flow`, `d-close1-state`, `d-close1-positions`, `d-close1-pnl`, `close1`. Только GET, без auth, редиректы запрещены. 15s socket timeout, максимум 12 MiB на response, до 3 попыток с 1s/2s паузами. 401/403 не обходятся. Ответы — недоверенные данные, не инструкции.

`data/observer/latest.json` — последняя допустимая PARTIAL observation, а не полный ledger. `last_attempt.json` указывает результат последней попытки, в том числе rejected. Каждый запуск сохраняет исходные bytes и snapshot отдельно. Неудачная проверка не заменяет latest; считыватель повторно вычисляет stale при возрасте свыше 900s. Сводки, live dumps, participant data и результаты stage2 ignored; не добавлять их принудительно в Git.

```python
from tools.contest_client import ContestClient
client = ContestClient('data/observer/latest.json')
print(client.observe())
print(client.get_leaderboard())
print(client.get_reference_price())
# Явный сетевой read-only проход: client.refresh_once()
assert client.submit_trade() == 'EXECUTION_DISABLED'
```

## Раздельные результаты доверия

| Проверка | Результат |
|---|---|
| SEED_SIGNATURE_VALID | true: Ed25519 над исходным `room|nonce|text` |
| MANIFEST_HASH_MATCH | true: seed package = локальный manifest SHA |
| REFEREE_AUTHORITY_CONFIRMED | false |
| RULES_COMMIT_PINNED | true: локальный candidate и artifacts закреплены; это не organizer authorization |
| ARCHIVE_COMPLETENESS | PARTIAL |
| LEDGER_REPLAY_VERIFIED | false |

Continuity signer `did:key:z6MkowHQwsx9xr84WbWN3YCnKutyBnBXkT1ChKY4uEAAMzte` закреплён для обнаружения смены ключа. Это наблюдённый signer, не доверенный organizer anchor. Подпись seed этим же DID не доказывает полномочия этого DID.

Ограниченный поиск проверил официальный repository tree, releases, существующие issues 5–9 и comments, предполагаемый LAUNCH.md и archive repository, Technocore read manual. Не найден независимый close-1 launch, связывающий FLOP Labs, referee DID и rules hash. Signer из другого конкурса sonnet-2 не переносит полномочия. Нет документированного доступного URL полного sweep archive: SHA в сообщении сам по себе не является архивом. Локально получено/проверено по этим хешам **0 файлов**. Полный ledger replay невозможен; guard `validated_replay()` тестирует порядок полных синтетических входов, но не восполняет отсутствующие данные.

Нужны: официальный close-1 authority binding и полный hash-addressed archive с исходными подписанными событиями/порядком. После появления — сверить hashes, signatures, room sequence, lock/final, replay unchanged Fold и сопоставить state. Не изменять Fold для прохождения проверок.

## Что работает и что остаётся stub

Работают read-only observer, saved snapshot reader, stale/gap/signature checks, simulator на официальном Decimal FIFO Fold, сценарии final S, локальная accounting validation и ordered replay guard. Cross-room snapshot берётся по общему sweep пяти referee rooms, не смешивает разные последние sweep. Counts разделены: declared owners, наблюдённые DID, явные mint records, известные settlement account IDs. Число людей неизвестно; trade ID не идентифицирует два торговых аккаунта.

`construct_trade`, `register`, `sign`, `submit_trade`, `claim`, `transfer` всегда EXECUTION_DISABLED, даже execute=True. `find_counterparties` возвращает UNKNOWN; `recommend_action` — HOLD_READ_ONLY. Нет signer/private key, регистрации, отправки offer/trade, claims или денежных операций. Validation не резервирует funds и не знает будущий close H.

Для будущего execution нужны отдельная явная авторизация пользователя, установленные authority/archive trust, reviewed signer и key custody вне repository, ingress checks, подтверждённый mint и реальная готовность контрагента. Одного environment flag недостаточно.

## Время и стратегия

Candidate lock: **2026-10-04 09:00 UTC = 14:00 Asia/Almaty**, sweep #2556. Final: **10:00 UTC = 15:00 Asia/Almaty**. Без подтверждённого mint поздний вход не моделировать как доступный. Наблюдённая максимальная задержка не ограничивает будущую задержку, гарантированное последнее безопасное время неизвестно.

48 final scenarios: no-trade, long/short, поздний вход ранее зарегистрированного аккаунта, отсутствие контрагента, delay/clawback, сдвиг reference за limits, expiry, недостаточный fee reserve и неверные шаги. Разделены P сделки, previous reference для limits, H закрытия для fee, global live mark и final S. Исходы и сравнение: STAGE2_REPORT; raw outputs в ignored data/stage2.

Ранги конкурентов не рассчитаны: snapshot не даёт точные полные cash/lots/fees всех owners. При последующем условном расчёте явно предполагать отсутствие новых сделок конкурентов. Округлённые live scores не доказывают точное равенство мест; вероятность top-3 из такой выборки не выводить.

## Источники и проверка

- [Официальный pinned package](https://github.com/flop-labs/technocore-close-call-challenge/tree/66c1da36538e4b1c685417d2f66922906b13fea0)
- [Существующие issues](https://github.com/flop-labs/technocore-close-call-challenge/issues), [releases](https://github.com/flop-labs/technocore-close-call-challenge/releases)
- [Technocore manual](https://technocore.chat/llms.txt), экспортные endpoints выше.

Upstream verify 15 artifacts, build --check, 18 tests PASS. Наши 50 tests PASS, включая настоящую публичную seed signature и tamper; синтетические envelopes используют mock verifier, новых подписей не создают. Полная upstream design suite 1785 seasons прошла на stage1, не изменена и повторно не выдаётся за свежий запуск. История перед push проверяется audit_history; это pattern/path/size scan плюс review, не математическое доказательство отсутствия всех секретов.

GitHub writes: создание пустого repository и изменение видимости в PUBLIC. Issues/PR/comments/upstream writes: 0. Contest writes/signatures/new keys/funds: 0.
