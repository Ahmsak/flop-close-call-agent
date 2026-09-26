# Исследование стратегий — только локально

**DRAFT/UNVERIFIED**, candidate package `66c1da36538e4b1c685417d2f66922906b13fea0`.
Это анализ конкурсных POLF, не инструкция по реальным финансовым операциям. Прогноз NVDA не строился; вероятность выигрыша и будущий threshold неизвестны.

## Общая модель

Все результаты считаются неизменённым official Fold через `tools/simulate_strategy.py`. `data/strategy_scenarios.json` содержит десять шаблонов A–J; `data/strategy_results.json` — 50 расчётов для final prices 180, 200, 210, 220, 400. Counterparties явно моделируются, имеют собственный cash и collateral. Это условные согласованные fills, а не доказательство доступной ликвидности. Ни один новый key/DID не создан.

**IMPLEMENTATION BEHAVIOR.** Для one-shot long `score=q(S-P)-F_L`, `F_L=q*max(fP,H-P)`; break-even `S=P+F_L/q`, для выигрыша над threshold T нужно строго `S>P+(T+F_L)/q`. Short: `score=q(P-S)-F_S`, `F_S=q*max(fP,P-H)`; break-even `S=P-F_S/q`, для score>T нужно `S<P-(T+F_S)/q`. При q=0 деление не применяется, score=0.

Если H=P, base fee означает необходимое движение более 1% в нужную сторону; для target T добавляется `T/(qP)`. Максимальная допустимая quantity открытия при известной H — округление вниз до 0.01 от `B/(P+fee_per_contract)`, и столько же должен профинансировать контрагент со своей fee. При B=10000, P=H=200: q_max=49.50, collateral=9900, fee=99, free cash=1. Запас в 1 POLF хрупок: изменение H повышает clawback и может сделать весь trade void. В основных примерах q=40 оставляет cash=1920.

Не надо складывать base fee и весь clawback: fee — максимум из них. Движение между подписанием и закрытием sweep, сделавшее entry выгодным, может полностью уйти в clawback. Для late-entry остаётся также час между lock и final S, в который закрыть риск уже нельзя.

## Сравнение A–J

**INFERENCE.** В таблице `F` — фактические совокупные fees, `R` — realized gross, `U` — unrealized gross. «Maximum loss» — сценарная граница при заданных fills, а не прогноз. У short отсутствует экономический stop; числовой cap парсера указан в RULES_ANALYSIS.

| Стратегия | Required move / break-even | Fee drag | Maximum loss | Attainable score | Время и контрагент |
|---|---|---|---|---|---|
| A. One-shot long | S>P+F/q; при H=P >1% вверх | Один entry: ≥1% notional | qP+F при S→0; не выше потраченного initial cash для единственного entry | q(S−P)−F; сверху экономически не ограничен | Больше времени под риском; нужен один seller с collateral |
| B. One-shot short | S<P−F/q; при H=P >1% вниз | Один entry | Неограничен при росте S; balance может <0 | До qP−F при S→0 | Нужен buyer; ранний вход дольше несёт asymmetric risk |
| C. Late-entry long | Та же формула от позднего P; движение до entry не заработок | Минимум 1%, возможен intrawindow clawback | qP+F | q(S−P_late)−F | Меньше time-to-S, но меньше времени найти seller, получить mint и исправить void |
| D. Late-entry short | Та же формула от позднего P вниз | Минимум 1%, возможен clawback | Неограничен | До qP_late−F | Те же latency/mint риски; финальный час без возможности выхода |
| E. Repeated trading | Сумма gross PnL всех legs > сумма F; roundtrip long требует P_out/P_in>(1+f)/(1−f)=1.020202… при H=trade price | ≥2 fees на roundtrip; k roundtrips примерно ≥2k% traded notional при близких ценах | Если есть shorts — неограничен; для long-only потери ограничены израсходованным капиталом, fees быстро его сокращают | R+U−ΣF, сильная зависимость от всего пути | Много повторных counterparties, FIFO, funds на fee до закрытия, риск неполного набора legs |
| F. Market making | Spread должен покрыть обе комиссии И favorable-price clawbacks | При неизменном H скидка bid и премия ask изымаются | Inventory long: qP+F; short inventory: неограничен; отсутствие второй стороны не даёт flat roundtrip | При фиксированном H полный пассивный roundtrip не даёт положительного score после clawback; при меняющемся H появляется directional inventory risk | Нет order book или приоритета maker; нужны два независимых fill и координация |
| G. Momentum | Движение после entry по сигналу должно превысить F/q и target/q | ≥1% на вход, больше при разворотах | Long ветка ограничена, short ветка неограничена | Та же directional формула; в сценариях нет статистически подтверждённого edge | Сигнал берётся до будущих H/S, исключить look-ahead; нужен контрагент, разделяющий противоположную оценку |
| H. Contrarian | Реальный последующий разворот должен превысить F/q | ≥1%; ловля падающего рынка может требовать дорогих корректировок | Short против роста неограничен; long против падения ограничен qP+F | Directional score, не гарантированный возврат к среднему | Нельзя считать предыдущее отклонение будущей прибылью; H clawback изымает apparent bargain |
| I. No-trade | Никакого движения не требуется | 0 | 0 конкурсных POLF | 0 | Только подтверждённая регистрация; контрагент не нужен; обходит отрицательные scores, но не положительные |
| J. Независимые owner accounts | Break-even отдельно для каждой стратегии; результаты не агрегируются для места | Каждая стратегия платит свои fees | Каждый short неограничен; multi-account не ограничивает общий downside | Отдельные scores, несколько мест возможны только по подтверждённым правилам | Условный анализ draft-разрешения; отдельные независимые внешние counterparties, без взаимных trades/перекачки |

Для E roundtrip break-even 2.0202% применим только при base fees; более сильный clawback повышает порог. Для полного закрытия нужно иметь свободный cash на fee до того, как closing proceeds попадут в cash. «Весь капитал в entry» может осложнить даже выход.

## Численные результаты official Fold

Условный путь: early entry 200; late entry 206; final S=210; quantity 40. Все значения POLF. Для E путь 200→206 (exit)→204 (re-entry)→208 (exit); для F buy 198 и sell 202 при H=200 на обоих sweep. G — momentum long после роста к 206; H — contrarian short на том же сигнале. Это иллюстрации, не обещание fills и не честное статистическое сравнение разных trading horizons.

| Стратегия | Gross PnL | Fees | Score |
|---|---:|---:|---:|
| A one-shot long | 400 | 80 | 320 |
| B one-shot short | −400 | 80 | −480 |
| C late long | 160 | 82.4 | 77.6 |
| D late short | −160 | 82.4 | −242.4 |
| E repeated | 400 realized | 327.2 | 72.8 |
| F market making | 160 realized | 160.8 | −0.8 |
| G momentum long | 160 | 82.4 | 77.6 |
| H contrarian short | −160 | 82.4 | −242.4 |
| I no-trade | 0 | 0 | 0 |
| J independent long / short / baseline | 400 / −400 / 0 | 80 / 80 / 0 | 320 / −480 / 0 |

F поясняет, почему «spread capture» не автоматическая прибыль: buyer fee=80 на цене198 и seller fee=80.8 на цене202. Здесь даже закрытый spread даёт −0.8. Мы не исследуем искусственные fills между своими keys, exploit, wash trading или spam. Запуск неизменённой upstream design suite, содержащей adversarial regression cases, служит проверкой опубликованных правил, а не разработкой подобных стратегий.

## Sensitivity и текущая планка

Signed public snapshot sweep #264, server timestamp 26 сентября 10:00:19 UTC: #3 live score **156.02**, mark **222.72**. Это не final threshold, и mark не равен Hyperliquid reference (224.39); нельзя экстраполировать его на 4 октября.

Только как условный target T=156.02: при P=H=200 и q=40 entry long должен получить S>205.9005 (минимальный cent S=205.91), short S<194.0995 (максимальный cent S=194.09). При q=49.50 и fee99 порог движения примерно 2.57596%; для late P=206,q=40,fee82.4 нужны S>211.9605 или S<200.0395. Строгое превышение важно: равенство score может разделить места с большой tie group. Сегодняшнее #3 не является прогнозом призовой планки.

Параметры для дальнейшего local research: разные final S, reference и H независимо; задержка регистрации на 1–6 sweep; отсутствие контрагента; проигрыш stamp race; дополнительный fee reserve; согласованные vs rejected fills; early и late entries на одном и том же synthetic path. Исторический backtest с реальными xyz:NVDA prints пока не выполнен; финальный print ещё в будущем. Ни один «победитель стратегии» по этим 50 сценариям не объявляется.

## Top 3 strategies to simulate next

1. **No-trade baseline**: нулевой score и tie handling, сравнение с распределением отрицательных результатов; без допущения, что регистрация гарантирована.
2. **One-shot directional entry с reserve**: симметрично long и short при одинаковых path и externally available counterparties; варьировать quantity, H drift и fee reserve, отдельно учитывать downside short.
3. **Late directional entry на уже подтверждённом account**: сравнить с ранним входом, закладывая missed ingestion, отказ counterparty и последний час после lock. Не основывать стратегию на создании key в последние минуты.

J не предлагается к live-применению до верификации authoritative launch и explicit user approval. По всей модели estimate_score не отправляет ни одной транзакции.
