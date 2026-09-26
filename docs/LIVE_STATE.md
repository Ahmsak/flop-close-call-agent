# Публичное состояние — read only

> Исторический snapshot stage1. Более позднее наблюдение sweep279 и раздельные trust/counts: [STAGE2_REPORT](STAGE2_REPORT.md). Для нового snapshot использовать observer из [HERMES_HANDOFF](HERMES_HANDOFF.md); stale пересчитывается при чтении.

Снимок получен **2026-09-26 10:02:51 UTC** (15:02:51 Asia/Qyzylorda). Последний общий для пяти комнат sweep **#264**, state timestamp **10:00:19.057634 UTC**. Это фиксированный снимок, не поток обновлений.

| Показатель | Значение |
|---|---:|
| Registered owner accounts | 1 141 897 |
| Уникальные люди/операторы | UNKNOWN |
| #1 live score | 163.60 POLF |
| #3 live score | 156.02 POLF |
| Live board mark (global VWAP) | 222.72 |
| Hyperliquid reference в price post | 224.39 |
| Reference trade time | 2026-09-26T09:59:55.703000Z |
| Reference trade id | 663907000390743 |
| Open interest, как опубликовано | 3 074 985.98 |
| Accounts с long / short | 73 523 / 74 606 |
| Registered trading rooms | 13 |
| Сумма reported settled counts в sweep 1–264 | 111 162 |
| Независимо полностью перепроверенное число trades | UNKNOWN |
| Sweeps с непустым missed | 32 |
| Максимальная наблюдаемая задержка flow против nominal cadence | 2500.826833 секунд, sweep #42 |

`data/live_snapshot.json` содержит top-25 и опубликованные top-10 positions, точные timestamps, reference и source metadata. Это частичные таблицы, не полная база всех accounts. Их записи не доказывают конечный prize результат: live scores маркируются global VWAP, а final score будет по S 4 октября. Большая группа делит score 156.02; displayed #3 не обязательно единоличное третье место.

## Подлинность и полнота

Проверены Ed25519 подписи 1321 сообщений в пяти exports. Подписант один и тот же, подписи покрывают room, nonce и text. SHA-256 seed manifest совпадает с локальным manifest и тегом close-1. Это не заменяет недостающую проверку launch authority для close-1: статус снимка **DRAFT/UNVERIFIED**. Server-assigned seq/ts не входят в подпись; timestamp отражает запись сервера, не независимо заверенное время.

Пять exports получены последовательно и сведены к последнему общему номеру sweep. Для каждого из 264 sweep сумма `len(mints)+omitted.mints` с начала совпадает с `state.owners`; итог 1 141 897, расхождений нет. Следовательно, отсутствие конкретного key в укороченном mints не доказывает отсутствие mint. Некоторые первоначальные issue reports этого не учитывали; более поздние комментарии исправляют вывод. Наш отчёт опирается на прямую сверку exports.

Число 111 162 — сумма `len(settled)+omitted.settled`. Оно сохранено как **reported aggregate**, а не как независимо replay-verified точный total. Полные sweep files, на которые ссылается поле `file`, по опубликованному URL не найдены; некоторые сообщения не имеют omitted, что само по себе не доказывает ни пропуск, ни полноту. Поэтому `trade_count` в JSON равен null, отдельно указан reported count / conservative lower bound. Цепочка открытого full-ledger replay и state-root verification недоступна.

Наличие `missed` и задержки больше 41 минуты делает любой расчёт «зарегистрироваться за пять минут» ненадёжным. Даже большой временной запас без individual mint confirmation не даёт гарантии. Данные не доказывают durable backlog, и мы не используем transaction probes для его проверки.

## Источники и способ чтения

Использованы только GET по документированным read endpoints, без credentials/signature и без redirects:

- [Price и seed](https://technocore.chat/r/d-close1-price/export)
- [State](https://technocore.chat/r/d-close1-state/export)
- [PnL / leaderboard](https://technocore.chat/r/d-close1-pnl/export)
- [Positions](https://technocore.chat/r/d-close1-positions/export)
- [Flow](https://technocore.chat/r/d-close1-flow/export)
- [Trading room retained export](https://technocore.chat/r/close1/export)
- [Live configuration](https://technocore.chat/config)

Владение пятью `d-` rooms также прочитано через `/kv/room-owners/<room>` и совпадает с подписантом; такое владение само по себе не authority. Точная ведомость URLs, HTTP statuses, hashes и headers хранится локально в `data/public_sources.json`. У пяти referee exports записи от начала до общего sweep сохранены; close1 — только retained window, не полная история.

Комментарии в [issue 6](https://github.com/flop-labs/technocore-close-call-challenge/issues/6) и [issue 7](https://github.com/flop-labs/technocore-close-call-challenge/issues/7) прочитаны как неподтверждённые сообщения участников, включая исправления первоначальных заявлений. Предложения участников отправлять probes не выполнялись.

Сырые exports, seed и snapshot оставлены локально и исключены из Git: upstream AGENTS.md требует не хранить participant data в repository. Агрегированный отчёт и инструмент проверки можно commit без публикации списка участников.
