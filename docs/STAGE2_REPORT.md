# Stage 2: observer и подготовка передачи

2026-09-26. Сводка дополняет stage1; текущее состояние Git/auth см. HERMES_HANDOFF.

## Реальный read-only fetch

Последний проверенный run: **11:20:32 UTC / 16:20:32 Asia/Almaty**, общий sweep **279**. На момент fetch reference age 425.42s, stale=false; это историческая отметка, при чтении age пересчитывается.

| Величина | Наблюдение |
|---|---:|
| Signed declared owner accounts | 1 195 316 |
| Уникальные DID в полученных referee payloads | 2 811 |
| Явные mint accounts в полученных записях | 2 401 |
| Account IDs исполненных сделок | UNKNOWN: settled summaries содержат trade IDs |
| Reported settled trades с учётом omitted counts | 134 176 |
| Люди | UNKNOWN |

SEED_SIGNATURE_VALID=true; MANIFEST_HASH_MATCH=true; RULES_COMMIT_PINNED=true. REFEREE_AUTHORITY_CONFIRMED=false; ARCHIVE_COMPLETENESS=PARTIAL; LEDGER_REPLAY_VERIFIED=false. Отсутствие verification errors в этом fetch не снимает эти ограничения. У trading-room export отсутствует начало истории: seq 1–1629325. Flow содержит omitted/missed records. Полные sweep files не получены (0), публичные SHA сохранены для будущей проверки; URL-контракт retrieval не найден.

Raw bytes, checks, source URLs/retrieval timestamps/hashes и room generation сохранены только локально в `data/observer/`. Данные участников не публикуются в истории Git. Public seed fixture содержит уже опубликованную referee-подпись, не приватный seed/key и не подпись, созданную нами.

## Final scenarios через официальный Fold

Начальный капитал 10 000 POLF. Quantity 40; обычный entry P=200, fee=80 на нашу сторону. Late account mint в sweep1, entry #2554 P=206, previous reference=205, H=207.20, fee=82.40. Таблица показывает наш final score, не live leaderboard mark и не место.

| Сценарий | S=180 | S=200 | S=210 | S=220 |
|---|---:|---:|---:|---:|
| No-trade control | 0 | 0 | 0 | 0 |
| Long | -880 | -80 | 320 | 720 |
| Short | 720 | -80 | -480 | -880 |
| Late confirmed long | -1122.40 | -322.40 | 77.60 | 477.60 |
| Late confirmed short | 957.60 | 157.60 | -242.40 | -642.40 |
| Delay + clawback (R=210, H=211, fee=440) | -1240 | -440 | -40 | 360 |

Ещё шесть вариантов × четыре S завершаются score=0: отсутствие контрагента (not submitted), price за limits после задержки, expiry, недостаточный reserve, invalid quantity step, invalid price step (void). Void не изображается исполненной сделкой. Всего 48 сценариев.

Для long без дополнительных сделок score=q(S−P)−fee, для short=q(P−S)−fee; фактический расчёт выполнен unchanged Fold с FIFO и Decimal. Late timing сам по себе не обеспечивает лучшую доходность. Фактические fills условны наличием контрагента, funds, ingestion и исполнением до expiry/lock. Контроль сохраняет нулевой score; его место среди остальных неизвестно.

В snapshot пересечение публикуемых top score IDs с top position IDs равно 0; даже совпадение не дало бы точных account cash/lots. Поэтому competitor final scores и conditional_place = null, global_rank_prediction=false. Предположение «после snapshot конкуренты не торгуют» явно сохранено для будущего моделирования, но само по себе не восполняет отсутствующие позиции. Округлённые leaderboard scores не являются доказательством exact ties. Прогноз top-3/вероятность выигрыша не сделан.

## Checks

- `scripts/verify.py`: 15 artifacts PASS; `scripts/build.py --check`: PASS.
- Upstream unittest: 18/18 PASS; наша suite: 50/50 PASS.
- 48 новых final scenarios построены; 1785 upstream design seasons были проверены stage1.
- Guards: after-final, duplicate/unordered sweep, missing sweep/archive, seed/package mismatch, signature tamper, key change, size/time/retry, stale read, cross-room common sweep и hashes, atomic snapshot preservation, live/final distinction.
- Upstream files не исправлялись. Послефинальный semantic gap и остальные observations остаются задокументированными; наша обёртка не является исправлением referee.
- История outgoing HEAD предварительно прошла audit без findings; финальный audit повторяется после commit. Ограничения scanner описаны в HERMES_HANDOFF.

Новых contest writes, подписей, keys, funds, issues/PR/comments нет. Observer не запускается автоматически в фоне.
