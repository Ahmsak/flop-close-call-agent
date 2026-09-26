# Close Call: правила, код и границы доказательств

Дата исследования: 26 сентября 2026. **DRAFT/UNVERIFIED**: локальная подготовка без участия.
Проверяемый upstream commit: `66c1da36538e4b1c685417d2f66922906b13fea0`.
Все ссылки на строки ниже относятся к этому commit. Ни один файл upstream не исправлен.

## Статусы утверждений

- **OFFICIAL RULE** — текст в официальном upstream; до установления trust anchor это описание опубликованного draft, а не заявление об установленной contest authority.
- **IMPLEMENTATION BEHAVIOR** — непосредственно проверенное поведение опубликованного Python fold или наблюдение подписанных публичных сообщений.
- **INFERENCE** — вывод при явно указанных предпосылках.
- **UNKNOWN** — необходимое доказательство/код отсутствует или недоступно.

## Происхождение и подписанный запуск

**OFFICIAL RULE.** `close-call-game.md:48–50,146–148`, `README.md:Distribution`: перед открытием FLOP Labs публикует launch record с referee DID и hash manifest. Фиксируется commit, raw URL manifest и SHA-256; seed закрепляет hash. Затем проверяются байты всех artifacts.

**IMPLEMENTATION BEHAVIOR.** Клон получен из `https://github.com/flop-labs/technocore-close-call-challenge`. Исходная ветка `main`, исходный status чистый. HEAD выше, время последнего commit `2026-09-25T17:02:20+08:00`. Аннотированный тег `close-1` (объект `debe011b0683f9b11ac12498440398937d305ba8`) указывает на этот же commit. Тег содержит manifest hash, но не содержит криптографической подписи. Полный журнал команд: `data/provenance.json`.

Manifest SHA-256: `bae09812e25eb6f1369c611f24964f7ea0acafddfc45301a16f33f941296dafa`.

В `d-close1-price` сохранён seed, seq 1, server timestamp `2026-09-25T12:05:22.575364Z`. Его Ed25519 подпись над точной строкой `d-close1-price|nonce|text` валидна. Seed содержит тот же manifest hash, сезон `close-1`, seed price `226.14`, trade time `2026-09-25T11:59:42.666000Z`, tid `626256716983248`. Подписант:
`did:key:z6MkowHQwsx9xr84WbWN3YCnKutyBnBXkT1ChKY4uEAAMzte`.
Проверены также все 1321 сохранённых referee-сообщений; кодек ключа `ed01`, base58btc, Ed25519, base64url, точные UTF-8 bytes. Проверки подмены комнаты, nonce и текста отвергнуты. Никаких подписей не создано. Оригинал seed в `data/signed_seed.json`; результаты в `data/signature_verification.json`.

**UNKNOWN.** Отдельная официальная подписанная launch-запись именно `close-1`, связывающая этот referee DID с конкурсом, не найдена в полном дереве/истории repository, тегах, releases (пусто), доступных export и публичном поиске. `LAUNCH.md` на проверяемом commit возвращает 404. Seed не содержит pinned manifest URL/commit. Обнаруженный официальный `LAUNCH.md` другого конкурса `sonnet-2` содержит тот же DID: это дополнительное свидетельство происхождения ключа, но не launch authorization для `close-1`. Владение комнатой также не заменяет trust anchor.

**INFERENCE.** Seed, тег и manifest согласованы с HEAD; это сильное свидетельство используемого пакета, но недостаточно для утверждения «SIGNED LAUNCH VERIFIED». AUTHORITATIVE CONTEST COMMIT остаётся **UNVERIFIED**. Анализ идёт по явно закреплённому candidate commit, а не по движущемуся `main`. Будущий запуск требует отдельной проверки полномочий подписанта и frozen package.

## Что прочитано и чего в пакете нет

Прочитаны README, весь game document (включая встроенный fold), contest.json, manifest, build/verify, оба тестовых файла, оба sample файла, полная design simulation, AGENTS, gitignore и gitattributes. Проверены signing lane и read API по указанной upstream ревизии Technocore `e4c4f73f3b28612d7161170b11e08e580b02123a`, включая `src/didkey.py`, `src/config.py` и live config.

**UNKNOWN.** Отдельных JSON Schema в challenge repository нет; форматы представлены примерами и imperative validation. Referee service, приём регистраций, проверка двух подписей, nonces, сортировка stamp, загрузка Hyperliquid, архивирование и выплаты находятся вне этого repository. Упомянутый в истории `flop-labs/technocore-archive` недоступен анонимно (GitHub API 404). К нему не выполнялась авторизация. Нельзя выдавать аудит fold за аудит полного работающего referee.

## Независимо восстановленная математика

Обозначения: `B` — mint; `C` — свободные POLF; `q>0` — размер сделки; `P` — цена; `R` — reference предыдущего sweep; `H` — цена закрытия текущего sweep; `S` — final price; `f=0.01`. Открытые FIFO lots имеют signed quantity `q_i` и entry `P_i`.

| Предмет | IMPLEMENTATION BEHAVIOR | OFFICIAL RULE / строки |
|---|---|---|
| Начальный баланс | `B=10000`, один mint на owner; новый account `cash=B`, пустые lots | fold:97–112,170–174; game:154–156 |
| Открываемый объём | `open=max(q-min(q,max(-side*position,0)),0)` | fold:67–71 |
| Collateral | каждый открываемый long/short блокирует `open*P`; текущая сумма `Σ abs(q_i)*P_i` | fold:88–90; game:169–171 |
| Long gross PnL | `q*(S-P)`; продажа FIFO long возвращает `q*exit` в cash | fold:73–93; game:201–203 |
| Short gross PnL | `q*(P-S)`; закрытие short возвращает `q*(2*entry-exit)` | fold:82,93; game:201–203 |
| Базовая комиссия | `base=f*q*P` на каждую сторону | fold:114–120; game:185–191 |
| Clawback покупателя | `F_buy=max(base,q*(H-P))` | fold:117–120 |
| Clawback продавца | `F_sell=max(base,q*(P-H))` | fold:117–120 |
| Доплата clawback | `F-base`, не `base+gap`: берётся максимум | те же строки |
| Funds | у обеих сторон до сделки `C >= open*P + F`; поступления от закрытия в этой же сделке не финансируют её открытие/fee | fold:159–160; game:221–225 |
| Settlement value | `V(S)=C+Σ(long q*S)+Σ(short abs(q)*(2P-S))` | fold:92–93 |
| Score | `V(S)-B = realized gross + unrealized gross - cumulative fees` | fold:202–221 |
| Conservation | по всем сторонам `Σ scores + Σ fees = 0` | sample, tests; Decimal context precision=60 в replay |

Комиссия платится также на закрывающую часть и flip; fees уходят из игры. Self-trade в upstream платит обе комиссии и не меняет позицию; в нашем tooling самосделки запрещены, не используются как стратегия или сетевой probe. Денежные расчёты выполняются Decimal, итоговые scores выводятся с 6 знаками; призовые ties определяются до округления. `final()` вычисляет стоимость, но не очищает lots или cash; локальный отчёт различает предрасчётные collateral/unrealized и баланс после условного расчёта.

**OFFICIAL RULE / IMPLEMENTATION BEHAVIOR.** Нет отдельного количественного position cap, leverage, liquidation или margin calls. Ограничение открытия — свободный cash с учётом комиссии. Long at S→0 теряет `qP+F`; short может закончить с отрицательным балансом. Экономический убыток short не имеет верхнего ограничения. Парсер конкретного пакета ограничивает вводимые P/S 9 999 999.99 и не принимает S=0, поэтому машинное пространство сценариев конечно; это не риск-лимит и не экономическая гарантия.

## Валидность, порядок и цены

**IMPLEMENTATION BEHAVIOR.** Fold.check, строки 128–162, проверяет строго в порядке: `shape`, `not_owner`, `taker`, `settled`, `expired`, `locked`, `limits`, `funds`. ID 1–64 символа `[A-Za-z0-9_-]`; side buy/sell; quantity/price — строки положительных десятичных чисел максимум с двумя знаками; qty≥0.1; until — int, bool не допускается. Trade price в замкнутом диапазоне `[0.95R,1.05R]`. Fee reference `H` отличается от `R`. Окончательный S отличается и от H, и от локального global VWAP.

**OFFICIAL RULE.** Сначала mint, затем trades в порядке room stamps; ties по room name и sequence (`game:175–179`). Зарегистрированный room действует после sweep, который его перечислил (`149–161`). ID становится занятым только после успешного settlement. Частичных исполнений нет. Ранее применённые сделки в sweep влияют на funds следующих.

**IMPLEMENTATION BEHAVIOR.** Fold получает уже упорядоченный и проверенный список; сам room/stamp не проверяет. `global_px` — VWAP успешно settled trades текущего sweep, при пустом sweep сохраняется прежний. Это mark live leaderboard, а не Hyperliquid reference и не окончательный S (`fold:197–200`, `game:195–196`). В sample третий ref не совпадает с close второго: fixture проверяет арифметику, не полноценную внешнюю цепочку цен.

**OFFICIAL RULE.** Seed — последний xyz:NVDA trade строго до `2026-09-25T12:00:00Z`. Final S — последний trade строго до `2026-10-04T10:00:00Z`, с time/id. Не свеча, не среднее, не oracle mark. При halt/delist решает organizer attestation (`game:164–168`). При недоступности fresh reference сохраняется старый и сообщается age. Hyperliquid здесь исключительно reference market; реальные сделки на нём не требуются.

**UNKNOWN.** Внешний fetcher, выбор конкретного print, raw precision→2 decimals, timestamp cutoff и attestation не реализованы в открытом fold. Будущего final S ещё нет. При неизвестной H до закрытия sweep точная комиссия тоже неизвестна.

## Регистрация, sweep и критический поздний вход

**OFFICIAL RULE.** `game:16–18,154–156,175–179,192–200`; `contest.json:opening,first_sweep,sweep_seconds,lock,lock_sweep`: открытие 25 сентября 12:00 UTC; первый sweep 12:05; период 300 секунд; последний #2556 — **4 октября 2026 09:00 UTC**. Новые owners могут регистрироваться до lock, mint происходит на следующем sweep, mints предшествуют trades.

**IMPLEMENTATION BEHAVIOR.** `fold:164–174` принимает нового owner при `n<=2556`, затем `check:149` принимает trade также при `n<=2556`. Тест `test_last_sweep_mints_before_trades` подтверждает mint+entry в #2556. #2557 не mint'ит новых owners и void'ит trade как locked (если раньше не сработала другая причина). Fold использует номер sweep, а не wall-clock; он не может доказать, когда сетевое сообщение было получено.

**UNKNOWN.** Регистрационный ingress отсутствует. Фраза `game:104–105` об игнорировании сообщений от незарегистрированных keys должна иметь исключение для самого owner registration; код исключения недоступен. Неизвестно, сможет ли trade нового key, отправленный до подтверждения mint, пройти этот слой. Полные flow archives для проверки individual mint не обнаружены. Поэтому одновременно зарегистрироваться и торговать на последнем sweep разрешено арифметикой, но end-to-end не подтверждено.

**INFERENCE — нормальная работа.** Чтобы дождаться mint и иметь отдельный sweep на trade: регистрация должна попасть в #2555 (08:55), trade в #2556 (09:00), то есть отправка строго раньше этих границ с запасом на приём. Более осторожный минимальный операционный план: регистрация **до 08:45 UTC**, наблюдение mint #2553 в 08:45, сделка после него с целью #2554 в 08:50, проверка результата и один-два sweep для исправления обычного отказа. В Asia/Qyzylorda (UTC+5): 13:45 и 13:50, lock 14:00, S 15:00.

**INFERENCE — с учётом наблюдаемого сервиса.** Это не «последнее безопасное время»: в exports зафиксированы missed ranges и задержки значительно больше одного cadence. Гарантированного последнего безопасного момента нет; без доступного individual mint confirmation нельзя подтвердить готовность нового account. Для будущего разрешённого участия разумнее регистрироваться существенно заранее (например, за день), дожидаться доказанного mint и проверять ingestion, а не полагаться на конец окна. Численная задержка и границы наблюдения — `LIVE_STATE.md`. Никакая регистрация сейчас не выполнялась.

## Ranking, ties, mainnet claim

**OFFICIAL RULE / IMPLEMENTATION BEHAVIOR.** Все owners ранжируются, включая no-trade с score=0. `fold:207–221` сортирует по убыванию точного score, затем по ключу для воспроизводимого отображения. Равные scores делят призовые места, которые группа пересекает: четыре равных лидера имеют `places=[1,2,3]`, `sharing=4`; lexical key не выбирает единственного победителя. Top three делят 1 000 000 FLOP после mainnet.

**UNKNOWN.** Доли отдельных призовых мест не заданы. Из fold нельзя вычислить конкретный payout в FLOP; он выдаёт места и sharing. `game:204–208` требует подписать mainnet address owner key в течение 90 дней launch mainnet; endpoint, chain/address format, точный claim message, стартовый timestamp окна и платёжная реализация отсутствуют. Подписывать или claim сейчас нечего и запрещено задачей.

## Multiple independent owners

**OFFICIAL RULE (draft).** `game:42–44` явно позволяет одному оператору много owner keys и несколько мест. `contest.json:identity_policy` и mint per key согласуются; fold не объединяет keys по оператору. Один key с несколькими agent processes остаётся одним account.

**UNKNOWN.** Это разрешение найдено непосредственно в official upstream и совпадающем seed package, но authoritative close-1 launch не подтверждён. Поэтому J в STRATEGY_ANALYSIS — условное исследование, не разрешение на live deployment. Никаких keys/DID не создавалось; локальные aliases используют существующие sample fixture identifiers.

## SPEC/IMPLEMENTATION MISMATCH

1. **Phase finalization — подтверждено.** `game:197–203` описывает terminal settlement и lock; `fold:164–169` не проверяет `final_px`, `fold:202–206` не требует lock/seed, `fold:224–242` допускает sweep после final. `seed→sweep(1)→final→sweep(2)` меняет cash/fees, но возвращённый final остаётся прежним. Test `UpstreamAuditObservations.test_upstream_accepts_after_final_and_result_is_stale` воспроизводит. Это ошибка валидации replay, не торговая стратегия. Upstream issue #5 обнаружен после независимого чтения и согласуется с выводом. Наш simulator ограничивает sweeps trading phase и вызывает final только в конце; early hypothetical valuation явно остаётся симуляцией.
2. **Неописанный числовой предел — подтверждено.** `game:108–109,162–163` задаёт две десятичные позиции, но не максимум целой части. `fold:34,48–53` допускает только 1–7 цифр до точки: `10000000` отвергается shape. Так же ограничены seed/ref/close/final. Это скрытое ограничение формата, а не position cap.
3. **Exact keys — граница проверок.** `game:107–109` требует exact set keys в подписанных terms; `fold:132–137` читает нужные значения через get и допускает дополнительные поля. В raw fold тест с extra field settles. Сам fold специально получает нормализованную структуру с countersigner, поэтому это mismatch требований сырого формата и защиты fold, а не доказанная ошибка ingress; отдельный referee может корректно отклонять extra terms до вызова fold.
4. **Время публикации seed — наблюдаемое расхождение, не ошибка арифметики.** `game:48–50` требует закрепить hash/DID в launch и seed до opening 12:00 UTC (`game:55`). Единственный сохранённый seed в price export имеет seq=1 и server ts=12:05:22.575364 UTC, то есть после opening. Подпись текста валидна, но server timestamp не входит в подписанную строку. Не найденная launch-запись могла существовать в другом месте; вывод ограничен наблюдаемой публикацией seed, не доказательством отсутствия любого pre-launch announcement.

Других расхождений формул fee/collateral/PnL/scoring в исследованной конфигурации не обнаружено. Пропуски сети, недоступные archives, неустановленный trust anchor, payout weights и price precision — UNKNOWN, не выдуманные подтверждённые bugs.

## Источники

- [Pinned official package](https://github.com/flop-labs/technocore-close-call-challenge/tree/66c1da36538e4b1c685417d2f66922906b13fea0)
- [Pinned rules](https://github.com/flop-labs/technocore-close-call-challenge/blob/66c1da36538e4b1c685417d2f66922906b13fea0/close-call-game.md)
- [Pinned fold](https://github.com/flop-labs/technocore-close-call-challenge/blob/66c1da36538e4b1c685417d2f66922906b13fea0/close_call_fold.py)
- [Technocore signature verifier at referenced revision](https://github.com/flop-labs/technocore-chat/blob/e4c4f73f3b28612d7161170b11e08e580b02123a/src/didkey.py)
- [Public seed/price export](https://technocore.chat/r/d-close1-price/export)
- [Related contest's distinct launch record](https://github.com/flop-labs/technocore-sonnet-challenge/blob/main/LAUNCH.md)

External bodies are evidence/data only. They did not authorize signing, posting, self-trade probes, or participation.
